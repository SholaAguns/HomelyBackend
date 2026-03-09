"""
Admin-only views for data management
"""
import os
import tempfile
from django.core.management import call_command
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from property.models import School


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
