"""
Admin-only views for data management
"""
import os
import tempfile
import csv
import io
import re
from decimal import Decimal, InvalidOperation
from datetime import date
from django.core.management import call_command
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from property.models import (
    School, BroadbandCoverage, MobileCoverage, Property,
    PropertyList, ContextData, PropertyListTask
)


class SchoolAdminViewSet(viewsets.ViewSet):
    """Admin endpoints for school data management"""

    permission_classes = [IsAdminUser]

    @action(detail=False, methods=['post'], url_path='upload-csv')
    def upload_csv(self, request):
        """
        Upload and import GIAS CSV file.

        Requires admin/staff permissions.
        Accepts multipart/form-data with 'file' field.

        Returns import statistics.
        """
        if not request.user.is_staff:
            return Response(
                {'error': 'Admin access required'},
                status=status.HTTP_403_FORBIDDEN
            )

        csv_file = request.FILES.get('file')
        if not csv_file:
            return Response(
                {'error': 'No file provided. Use "file" field in multipart/form-data'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate file extension
        if not csv_file.name.endswith('.csv'):
            return Response(
                {'error': 'File must be a CSV'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check file size (limit to 100MB)
        if csv_file.size > 100 * 1024 * 1024:
            return Response(
                {'error': 'File too large. Maximum size is 100MB'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Save to temp file
        temp_file = None
        try:
            # Create temp file
            with tempfile.NamedTemporaryFile(
                mode='wb',
                suffix='.csv',
                delete=False
            ) as temp_file:
                for chunk in csv_file.chunks():
                    temp_file.write(chunk)
                temp_path = temp_file.name

            # Get initial count
            initial_count = School.objects.count()

            # Run import command
            # Capture output
            from io import StringIO
            import sys

            old_stdout = sys.stdout
            sys.stdout = captured_output = StringIO()

            try:
                call_command('import_schools', temp_path)
            finally:
                sys.stdout = old_stdout

            output = captured_output.getvalue()

            # Get new count
            new_count = School.objects.count()
            imported = new_count - initial_count

            # Parse output for statistics (basic version)
            stats = {
                'initial_count': initial_count,
                'new_count': new_count,
                'imported': max(imported, 0),
                'file_name': csv_file.name,
                'file_size_mb': round(csv_file.size / (1024 * 1024), 2),
                'output': output
            }

            return Response({
                'status': 'success',
                'message': f'Successfully imported schools',
                'statistics': stats
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {
                    'error': 'Import failed',
                    'message': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        finally:
            # Clean up temp file
            if temp_file and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except:
                    pass

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """Get school database statistics"""
        from django.db.models import Count, Q

        total = School.objects.count()
        open_schools = School.objects.filter(
            establishment_status__icontains='Open'
        ).count()

        # Count by phase
        phase_counts = School.objects.filter(
            establishment_status__icontains='Open'
        ).values('phase').annotate(count=Count('phase')).order_by('-count')

        # Count with/without coordinates
        with_coords = School.objects.exclude(
            Q(latitude__isnull=True) | Q(longitude__isnull=True)
        ).count()

        coord_percentage = (with_coords / total * 100) if total > 0 else 0

        return Response({
            'total_schools': total,
            'open_schools': open_schools,
            'closed_schools': total - open_schools,
            'schools_with_coordinates': with_coords,
            'coordinate_coverage_percent': round(coord_percentage, 1),
            'phase_breakdown': list(phase_counts[:10]),
            'latest_import': School.objects.order_by('-data_source_date').values('data_source_date').first()
        })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def upload_broadband_data(request):
    """
    Upload broadband coverage CSV data (admin only).

    POST /api/admin/broadband/upload/
    Body: multipart/form-data
        - file: CSV file
        - data_date: Optional YYYY-MM-DD (defaults to extract from filename)
        - clear: Optional boolean to clear existing data for this date
        - level: Optional 'oa' or 'laua' (defaults to 'oa')
    """
    if 'file' not in request.FILES:
        return Response(
            {'error': 'No file provided'},
            status=status.HTTP_400_BAD_REQUEST
        )

    csv_file = request.FILES['file']
    clear_existing = request.data.get('clear', 'false').lower() == 'true'
    level = request.data.get('level', 'oa')

    # Parse data date
    data_date_str = request.data.get('data_date')
    if data_date_str:
        try:
            data_date = date.fromisoformat(data_date_str)
        except ValueError:
            return Response(
                {'error': f'Invalid date format: {data_date_str}. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
    else:
        # Extract from filename
        match = re.search(r'(\d{4})(\d{2})', csv_file.name)
        if match:
            year, month = match.groups()
            data_date = date(int(year), int(month), 1)
        else:
            data_date = date.today()

    if clear_existing:
        count = BroadbandCoverage.objects.filter(data_date=data_date).count()
        BroadbandCoverage.objects.filter(data_date=data_date).delete()

    # Stats
    total_rows = 0
    imported = 0
    updated = 0
    skipped = 0
    errors = []

    # Try different encodings
    encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']
    reader = None

    for encoding in encodings:
        try:
            csv_file.seek(0)
            content = csv_file.read().decode(encoding)
            reader = csv.DictReader(io.StringIO(content))
            # Test read first row
            next(reader)
            # Reset
            reader = csv.DictReader(io.StringIO(content))
            break
        except (UnicodeDecodeError, StopIteration):
            continue

    if not reader:
        return Response(
            {'error': 'Could not decode CSV file'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        records_to_create = []
        records_to_update = []

        for row in reader:
            total_rows += 1

            try:
                # Determine geographic code
                if level == 'oa':
                    oa_code = (row.get('output_area', '').strip() or
                              row.get('oa', '').strip() or
                              row.get('OA', '').strip())
                    laua_code = row.get('laua', '').strip() or row.get('LAUA', '').strip()
                    laua_name = row.get('laua_name', '').strip() or row.get('LAUA_name', '').strip()
                else:
                    oa_code = ''
                    laua_code = row.get('laua', '').strip() or row.get('LAUA', '').strip()
                    laua_name = row.get('laua_name', '').strip() or row.get('LAUA_name', '').strip()

                if not oa_code and not laua_code:
                    skipped += 1
                    continue

                identifier_code = oa_code if oa_code else laua_code

                def safe_decimal(value, default=None):
                    if not value or value == '':
                        return default
                    try:
                        return Decimal(str(value).strip())
                    except (ValueError, InvalidOperation):
                        return default

                record_data = {
                    'oa_code': identifier_code,
                    'laua_code': laua_code or '',
                    'laua_name': laua_name or '',
                    'avg_download_under_10': safe_decimal(
                        row.get('Average max download speed (Mbit/s) for lines <10Mbit/s', '')
                    ),
                    'avg_download_10_to_30': safe_decimal(
                        row.get('Average max download speed (Mbit/s) for lines 10<30Mbit/s', '')
                    ),
                    'avg_download_30_to_100': safe_decimal(
                        row.get('Average max download speed (Mbit/s) for lines 30<100Mbit/s', '')
                    ),
                    'avg_download_100_to_300': safe_decimal(
                        row.get('Average max download speed (Mbit/s) for lines 100<300Mbit/s', '')
                    ),
                    'avg_download_300_to_900': safe_decimal(
                        row.get('Average max download speed (Mbit/s) for lines 300<900Mbit/s', '')
                    ),
                    'avg_download_over_900': safe_decimal(
                        row.get('Average max download speed (Mbit/s) for lines >=900Mbit/s', '')
                    ),
                    'avg_upload_under_10': safe_decimal(
                        row.get('Average max upload speed (Mbit/s) for lines <10Mbit/s', '')
                    ),
                    'avg_upload_10_to_30': safe_decimal(
                        row.get('Average max upload speed (Mbit/s) for lines 10<30Mbit/s', '')
                    ),
                    'avg_upload_30_to_100': safe_decimal(
                        row.get('Average max upload speed (Mbit/s) for lines 30<100Mbit/s', '')
                    ),
                    'avg_upload_100_to_300': safe_decimal(
                        row.get('Average max upload speed (Mbit/s) for lines 100<300Mbit/s', '')
                    ),
                    'avg_upload_300_to_900': safe_decimal(
                        row.get('Average max upload speed (Mbit/s) for lines 300<900Mbit/s', '')
                    ),
                    'avg_upload_over_900': safe_decimal(
                        row.get('Average max upload speed (Mbit/s) for lines >=900Mbit/s', '')
                    ),
                    'avg_monthly_usage_gb': safe_decimal(
                        row.get('Average monthly data usage (GB) per connection (all technologies)', '')
                    ),
                    'avg_monthly_usage_full_fibre_gb': safe_decimal(
                        row.get('Average monthly data usage (GB) per full-fibre connection', '')
                    ),
                    'full_fibre_takeup_pct_of_coverage': safe_decimal(
                        row.get('Full-fibre take-up (% of full-fibre coverage)', '')
                    ),
                    'full_fibre_takeup_pct_of_all': safe_decimal(
                        row.get('Full-fibre take-up (% of all premises)', '')
                    ),
                    'data_date': data_date,
                }

                existing = BroadbandCoverage.objects.filter(
                    oa_code=identifier_code,
                    data_date=data_date
                ).first()

                if existing:
                    for field, value in record_data.items():
                        setattr(existing, field, value)
                    records_to_update.append(existing)
                    updated += 1
                else:
                    records_to_create.append(BroadbandCoverage(**record_data))
                    imported += 1

                if len(records_to_create) >= 1000:
                    BroadbandCoverage.objects.bulk_create(records_to_create, ignore_conflicts=True)
                    records_to_create = []

                if len(records_to_update) >= 1000:
                    BroadbandCoverage.objects.bulk_update(
                        records_to_update,
                        fields=list(record_data.keys())
                    )
                    records_to_update = []

            except Exception as e:
                errors.append(f"Row {total_rows}: {str(e)}")
                if len(errors) > 100:
                    break

        # Insert/update remaining
        if records_to_create:
            BroadbandCoverage.objects.bulk_create(records_to_create, ignore_conflicts=True)

        if records_to_update:
            BroadbandCoverage.objects.bulk_update(
                records_to_update,
                fields=list(record_data.keys())
            )

    except Exception as e:
        return Response(
            {'error': f'Import failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return Response({
        'success': True,
        'data_date': data_date.isoformat(),
        'level': level,
        'stats': {
            'total_rows': total_rows,
            'imported': imported,
            'updated': updated,
            'skipped': skipped,
            'errors': len(errors),
        },
        'error_samples': errors[:10] if errors else []
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def upload_mobile_data(request):
    """
    Upload mobile coverage CSV data (admin only).

    POST /api/admin/mobile/upload/
    Body: multipart/form-data
        - file: CSV file
        - data_date: Optional YYYY-MM-DD (defaults to extract from filename)
        - clear: Optional boolean to clear existing data for this date
    """
    if 'file' not in request.FILES:
        return Response(
            {'error': 'No file provided'},
            status=status.HTTP_400_BAD_REQUEST
        )

    csv_file = request.FILES['file']
    clear_existing = request.data.get('clear', 'false').lower() == 'true'

    # Parse data date
    data_date_str = request.data.get('data_date')
    if data_date_str:
        try:
            data_date = date.fromisoformat(data_date_str)
        except ValueError:
            return Response(
                {'error': f'Invalid date format: {data_date_str}. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
    else:
        match = re.search(r'(\d{4})(\d{2})', csv_file.name)
        if match:
            year, month = match.groups()
            data_date = date(int(year), int(month), 1)
        else:
            data_date = date.today()

    if clear_existing:
        count = MobileCoverage.objects.filter(data_date=data_date).count()
        MobileCoverage.objects.filter(data_date=data_date).delete()

    # Stats
    total_rows = 0
    imported = 0
    updated = 0
    skipped = 0
    errors = []

    # Try different encodings
    encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']
    reader = None

    for encoding in encodings:
        try:
            csv_file.seek(0)
            content = csv_file.read().decode(encoding)
            reader = csv.DictReader(io.StringIO(content))
            next(reader)
            reader = csv.DictReader(io.StringIO(content))
            break
        except (UnicodeDecodeError, StopIteration):
            continue

    if not reader:
        return Response(
            {'error': 'Could not decode CSV file'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        records_to_create = []
        records_to_update = []

        for row in reader:
            total_rows += 1

            try:
                laua_code = row.get('laua', '').strip()
                laua_name = row.get('laua_name', '').strip()

                if not laua_code:
                    skipped += 1
                    continue

                def safe_decimal(value, default=None):
                    if not value or value == '':
                        return default
                    try:
                        return Decimal(str(value).strip())
                    except (ValueError, InvalidOperation):
                        return default

                def safe_int(value, default=None):
                    if not value or value == '':
                        return default
                    try:
                        return int(str(value).strip())
                    except (ValueError, TypeError):
                        return default

                record_data = {
                    'laua_code': laua_code,
                    'laua_name': laua_name,
                    'premise_count': safe_int(row.get('prem_count', '')),
                    'pixel_count': safe_int(row.get('pixel_count', '')),
                    'twog_premises_outdoor_0': safe_decimal(row.get('2G_prem_out_0', '')),
                    'twog_premises_outdoor_1': safe_decimal(row.get('2G_prem_out_1', '')),
                    'twog_premises_outdoor_2': safe_decimal(row.get('2G_prem_out_2', '')),
                    'twog_premises_outdoor_3': safe_decimal(row.get('2G_prem_out_3', '')),
                    'twog_premises_outdoor_4': safe_decimal(row.get('2G_prem_out_4', '')),
                    'twog_premises_indoor_0': safe_decimal(row.get('2G_prem_in_0', '')),
                    'twog_premises_indoor_1': safe_decimal(row.get('2G_prem_in_1', '')),
                    'twog_premises_indoor_2': safe_decimal(row.get('2G_prem_in_2', '')),
                    'twog_premises_indoor_3': safe_decimal(row.get('2G_prem_in_3', '')),
                    'twog_premises_indoor_4': safe_decimal(row.get('2G_prem_in_4', '')),
                    'threeg_premises_outdoor_0': safe_decimal(row.get('3G_prem_out_0', '')),
                    'threeg_premises_outdoor_1': safe_decimal(row.get('3G_prem_out_1', '')),
                    'threeg_premises_outdoor_2': safe_decimal(row.get('3G_prem_out_2', '')),
                    'threeg_premises_outdoor_3': safe_decimal(row.get('3G_prem_out_3', '')),
                    'threeg_premises_outdoor_4': safe_decimal(row.get('3G_prem_out_4', '')),
                    'threeg_premises_indoor_0': safe_decimal(row.get('3G_prem_in_0', '')),
                    'threeg_premises_indoor_1': safe_decimal(row.get('3G_prem_in_1', '')),
                    'threeg_premises_indoor_2': safe_decimal(row.get('3G_prem_in_2', '')),
                    'threeg_premises_indoor_3': safe_decimal(row.get('3G_prem_in_3', '')),
                    'threeg_premises_indoor_4': safe_decimal(row.get('3G_prem_in_4', '')),
                    'fourg_premises_outdoor_0': safe_decimal(row.get('4G_prem_out_0', '')),
                    'fourg_premises_outdoor_1': safe_decimal(row.get('4G_prem_out_1', '')),
                    'fourg_premises_outdoor_2': safe_decimal(row.get('4G_prem_out_2', '')),
                    'fourg_premises_outdoor_3': safe_decimal(row.get('4G_prem_out_3', '')),
                    'fourg_premises_outdoor_4': safe_decimal(row.get('4G_prem_out_4', '')),
                    'fourg_premises_indoor_0': safe_decimal(row.get('4G_prem_in_0', '')),
                    'fourg_premises_indoor_1': safe_decimal(row.get('4G_prem_in_1', '')),
                    'fourg_premises_indoor_2': safe_decimal(row.get('4G_prem_in_2', '')),
                    'fourg_premises_indoor_3': safe_decimal(row.get('4G_prem_in_3', '')),
                    'fourg_premises_indoor_4': safe_decimal(row.get('4G_prem_in_4', '')),
                    'fiveg_high_premises_outdoor_0': safe_decimal(row.get('5G_high_confidence_prem_out_0', '')),
                    'fiveg_high_premises_outdoor_1': safe_decimal(row.get('5G_high_confidence_prem_out_1', '')),
                    'fiveg_high_premises_outdoor_2': safe_decimal(row.get('5G_high_confidence_prem_out_2', '')),
                    'fiveg_high_premises_outdoor_3': safe_decimal(row.get('5G_high_confidence_prem_out_3', '')),
                    'fiveg_high_premises_outdoor_4': safe_decimal(row.get('5G_high_confidence_prem_out_4', '')),
                    'fiveg_very_high_premises_outdoor_0': safe_decimal(row.get('5G_very_high_confidence_prem_out_0', '')),
                    'fiveg_very_high_premises_outdoor_1': safe_decimal(row.get('5G_very_high_confidence_prem_out_1', '')),
                    'fiveg_very_high_premises_outdoor_2': safe_decimal(row.get('5G_very_high_confidence_prem_out_2', '')),
                    'fiveg_very_high_premises_outdoor_3': safe_decimal(row.get('5G_very_high_confidence_prem_out_3', '')),
                    'fiveg_very_high_premises_outdoor_4': safe_decimal(row.get('5G_very_high_confidence_prem_out_4', '')),
                    'voice_premises_outdoor_0': safe_decimal(row.get('Voice_prem_out_0', '')),
                    'voice_premises_outdoor_1': safe_decimal(row.get('Voice_prem_out_1', '')),
                    'voice_premises_outdoor_2': safe_decimal(row.get('Voice_prem_out_2', '')),
                    'voice_premises_outdoor_3': safe_decimal(row.get('Voice_prem_out_3', '')),
                    'voice_premises_outdoor_4': safe_decimal(row.get('Voice_prem_out_4', '')),
                    'voice_premises_indoor_0': safe_decimal(row.get('Voice_prem_in_0', '')),
                    'voice_premises_indoor_1': safe_decimal(row.get('Voice_prem_in_1', '')),
                    'voice_premises_indoor_2': safe_decimal(row.get('Voice_prem_in_2', '')),
                    'voice_premises_indoor_3': safe_decimal(row.get('Voice_prem_in_3', '')),
                    'voice_premises_indoor_4': safe_decimal(row.get('Voice_prem_in_4', '')),
                    'data_premises_outdoor_0': safe_decimal(row.get('Data_prem_out_0', '')),
                    'data_premises_outdoor_1': safe_decimal(row.get('Data_prem_out_1', '')),
                    'data_premises_outdoor_2': safe_decimal(row.get('Data_prem_out_2', '')),
                    'data_premises_outdoor_3': safe_decimal(row.get('Data_prem_out_3', '')),
                    'data_premises_outdoor_4': safe_decimal(row.get('Data_prem_out_4', '')),
                    'data_premises_indoor_0': safe_decimal(row.get('Data_prem_in_0', '')),
                    'data_premises_indoor_1': safe_decimal(row.get('Data_prem_in_1', '')),
                    'data_premises_indoor_2': safe_decimal(row.get('Data_prem_in_2', '')),
                    'data_premises_indoor_3': safe_decimal(row.get('Data_prem_in_3', '')),
                    'data_premises_indoor_4': safe_decimal(row.get('Data_prem_in_4', '')),
                    'data_date': data_date,
                }

                existing = MobileCoverage.objects.filter(
                    laua_code=laua_code,
                    data_date=data_date
                ).first()

                if existing:
                    for field, value in record_data.items():
                        setattr(existing, field, value)
                    records_to_update.append(existing)
                    updated += 1
                else:
                    records_to_create.append(MobileCoverage(**record_data))
                    imported += 1

                if len(records_to_create) >= 500:
                    MobileCoverage.objects.bulk_create(records_to_create, ignore_conflicts=True)
                    records_to_create = []

                if len(records_to_update) >= 500:
                    MobileCoverage.objects.bulk_update(
                        records_to_update,
                        fields=list(record_data.keys())
                    )
                    records_to_update = []

            except Exception as e:
                errors.append(f"Row {total_rows}: {str(e)}")
                if len(errors) > 100:
                    break

        # Insert/update remaining
        if records_to_create:
            MobileCoverage.objects.bulk_create(records_to_create, ignore_conflicts=True)

        if records_to_update:
            MobileCoverage.objects.bulk_update(
                records_to_update,
                fields=list(record_data.keys())
            )

    except Exception as e:
        return Response(
            {'error': f'Import failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return Response({
        'success': True,
        'data_date': data_date.isoformat(),
        'stats': {
            'total_rows': total_rows,
            'imported': imported,
            'updated': updated,
            'skipped': skipped,
            'errors': len(errors),
        },
        'error_samples': errors[:10] if errors else []
    })


# ===== DASHBOARD ENDPOINTS =====

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_dashboard_statistics(request):
    """Get overall system statistics for admin dashboard"""
    from django.db.models import Count, Avg
    from datetime import timedelta

    # Property statistics
    total_properties = Property.objects.count()
    properties_by_state = dict(
        Property.objects.values('state')
        .annotate(count=Count('id'))
        .values_list('state', 'count')
    )
    avg_price = Property.objects.aggregate(avg=Avg('price'))['avg']

    # Property List statistics
    total_lists = PropertyList.objects.count()
    active_lists = PropertyList.objects.filter(state='ACTIVE').count()

    # Recent properties (last 7 days)
    seven_days_ago = timezone.now() - timedelta(days=7)
    recent_properties = Property.objects.filter(created_at__gte=seven_days_ago).count()

    # Context Data statistics
    context_stats = {
        'pending': ContextData.objects.filter(status='PENDING').count(),
        'in_progress': ContextData.objects.filter(status='IN_PROGRESS').count(),
        'complete': ContextData.objects.filter(status='COMPLETE').count(),
        'failed': ContextData.objects.filter(status='FAILED').count(),
    }

    # Task statistics
    task_stats = {
        'queued': PropertyListTask.objects.filter(status='QUEUED').count(),
        'in_progress': PropertyListTask.objects.filter(status='IN_PROGRESS').count(),
        'completed': PropertyListTask.objects.filter(status='COMPLETED').count(),
        'failed': PropertyListTask.objects.filter(status='FAILED').count(),
    }

    return Response({
        'properties': {
            'total': total_properties,
            'by_state': properties_by_state,
            'avg_price': float(avg_price) if avg_price else 0,
            'recent_count': recent_properties,
        },
        'lists': {
            'total': total_lists,
            'active': active_lists,
        },
        'context_services': context_stats,
        'tasks': task_stats,
        'last_updated': timezone.now().isoformat(),
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_system_status(request):
    """Get system health and status information"""
    from property.models import StateTransitionLog

    # Failed services needing attention
    failed_services = ContextData.objects.filter(status='FAILED').select_related('property')[:10]

    # Active tasks with progress
    active_tasks = PropertyListTask.objects.filter(
        status='IN_PROGRESS'
    ).select_related('property_list')[:10]

    # Recent state transitions (audit log)
    recent_transitions = StateTransitionLog.objects.select_related(
        'triggered_by', 'content_type'
    )[:20]

    return Response({
        'failed_services': [
            {
                'id': fs.id,
                'service_name': fs.service_name,
                'property_uuid': str(fs.property.uuid),
                'property_title': fs.property.title,
                'error_message': fs.error_message,
                'retry_count': fs.retry_count,
                'last_attempt': fs.last_attempt_at.isoformat() if fs.last_attempt_at else None,
            }
            for fs in failed_services
        ],
        'active_tasks': [
            {
                'id': task.id,
                'uuid': str(task.uuid),
                'task_type': task.task_type,
                'list_uuid': str(task.property_list.uuid),
                'list_title': task.property_list.title,
                'progress': task.progress_percentage,
                'total_items': task.total_items,
                'completed_items': task.completed_items,
                'failed_items': task.failed_items,
            }
            for task in active_tasks
        ],
        'recent_activity': [
            {
                'id': log.id,
                'from_state': log.from_state,
                'to_state': log.to_state,
                'transition': log.transition_name,
                'user': log.triggered_by.username if log.triggered_by else 'System',
                'timestamp': log.timestamp.isoformat(),
            }
            for log in recent_transitions
        ],
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_retry_context_service(request, context_data_id):
    """Retry a failed context service"""
    from property.services.stage2_orchestrator import Stage2Orchestrator

    try:
        context_data = ContextData.objects.select_related('property').get(id=context_data_id)

        if context_data.status != 'FAILED':
            return Response(
                {'error': 'Can only retry failed services'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Reset status
        context_data.status = 'PENDING'
        context_data.retry_count += 1
        context_data.error_message = ''
        context_data.save()

        # Trigger orchestrator
        orchestrator = Stage2Orchestrator()
        orchestrator.process_property(context_data.property.id)

        return Response({
            'success': True,
            'message': f'Retrying {context_data.service_name} for {context_data.property.title}'
        })

    except ContextData.DoesNotExist:
        return Response({'error': 'Service not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_cancel_task(request, task_uuid):
    """Cancel a queued or active task"""
    try:
        task = PropertyListTask.objects.get(uuid=task_uuid)

        if task.status not in ['QUEUED', 'IN_PROGRESS']:
            return Response(
                {'error': 'Can only cancel queued or in-progress tasks'},
                status=status.HTTP_400_BAD_REQUEST
            )

        task.status = 'CANCELLED'
        task.completed_at = timezone.now()
        task.save()

        return Response({
            'success': True,
            'message': f'Task {task.get_task_type_display()} cancelled'
        })

    except PropertyListTask.DoesNotExist:
        return Response({'error': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_bulk_delete_properties(request):
    """Bulk delete properties by UUIDs"""
    property_uuids = request.data.get('property_uuids', [])

    if not property_uuids:
        return Response({'error': 'No property UUIDs provided'}, status=status.HTTP_400_BAD_REQUEST)

    deleted_count, _ = Property.objects.filter(uuid__in=property_uuids).delete()

    return Response({'success': True, 'deleted_count': deleted_count})


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_bulk_stage_transition(request):
    """Bulk trigger stage transitions for properties"""
    property_uuids = request.data.get('property_uuids', [])
    action = request.data.get('action')  # 'run_stage2', 'run_stage3', 'rerun_services'

    if not property_uuids or not action:
        return Response(
            {'error': 'Missing property_uuids or action'},
            status=status.HTTP_400_BAD_REQUEST
        )

    properties = Property.objects.filter(uuid__in=property_uuids)
    success_count = 0
    errors = []

    for prop in properties:
        try:
            if action == 'run_stage2' and prop.state in ['NEW', 'STAGE2_COMPLETE']:
                prop.run_stage2()
                prop.save()
                success_count += 1
            elif action == 'run_stage3' and prop.state in ['STAGE2_COMPLETE', 'STAGE3_COMPLETE']:
                prop.run_stage3()
                prop.save()
                success_count += 1
            elif action == 'rerun_services' and prop.state in ['STAGE2_COMPLETE', 'STAGE3_IN_PROGRESS', 'STAGE3_COMPLETE']:
                prop.rerun_services()
                prop.save()
                success_count += 1
        except Exception as e:
            errors.append({'property_uuid': str(prop.uuid), 'error': str(e)})

    return Response({
        'success': True,
        'processed_count': success_count,
        'errors': errors,
    })
