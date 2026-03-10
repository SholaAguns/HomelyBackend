"""
Admin views for data management
"""
import csv
import io
import re
from decimal import Decimal, InvalidOperation
from datetime import date
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from property.models import BroadbandCoverage, MobileCoverage


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
