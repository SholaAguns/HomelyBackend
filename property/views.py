import logging
from uuid import uuid4

from django.conf import settings
from django.contrib.auth.models import User
from django.core import signing
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample

logger = logging.getLogger('property.views')

from property.models.stage1_models import *
from property.serializers import *
from property.models.stage2_models import ContextData, ContextOptions
from property.models.stage3_models import RatingCriteria, Criterion, CriterionScore
from property.models.models_poi import PlaceOfInterest
from property.tasks import retrieve_context_data, calculate_property_rating, scrape_rightmove_properties, bulk_calculate_project_ratings
from property.services import property_creation_service_factory
from property.utils.invitation_tokens import generate_invite_token, verify_invite_token, hash_token
from property.utils.notifications import create_notification
from property.permissions import require_project_owner, require_project_contributor, check_project_contributor
from django.db.models import Q, Avg


class ProjectViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Project CRUD operations.
    Users can access projects they own, view, or contribute to.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ProjectSerializer
    lookup_field = 'uuid'

    def get_queryset(self):
        """Filter to projects user owns, views, or contributes to"""
        user = self.request.user
        return Project.objects.filter(
            Q(owner=user) |
            Q(viewers=user) |
            Q(contributors=user)
        ).distinct()

    @require_project_contributor()
    def update(self, request, *args, **kwargs):
        """Update project - owner or contributor only"""
        return super().update(request, *args, **kwargs)

    @require_project_contributor()
    def partial_update(self, request, *args, **kwargs):
        """Partial update project - owner or contributor only"""
        return super().partial_update(request, *args, **kwargs)

    @require_project_owner()
    def destroy(self, request, *args, **kwargs):
        """Delete project - owner only"""
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['get'], url_path='context-options')
    def context_options(self, request, uuid=None):
        """
        GET /api/property/projects/{uuid}/context-options/

        Get or create context options for project (inline setup support).
        """
        project = self.get_object()

        # Get or create context options
        context_options, created = ContextOptions.objects.get_or_create(
            project=project
        )

        serializer = ContextOptionsSerializer(context_options)
        return Response({
            **serializer.data,
            'is_configured': any([
                context_options.enable_crime,
                context_options.enable_schools,
                context_options.enable_broadband,
                context_options.enable_mobile,
                context_options.enable_poi,
                context_options.enable_council_tax,
                context_options.enable_saved_locations
            ])
        })

    @context_options.mapping.put
    @context_options.mapping.patch
    @require_project_contributor()
    def update_context_options(self, request, uuid=None):
        """
        PUT/PATCH /api/property/projects/{uuid}/context-options/

        Update project context options.
        """
        project = self.get_object()

        context_options, created = ContextOptions.objects.get_or_create(
            project=project
        )

        serializer = ContextOptionsSerializer(
            context_options,
            data=request.data,
            partial=request.method == 'PATCH'
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def stats(self, request, uuid=None):
        """
        GET /api/property/projects/{uuid}/stats/

        Get comprehensive project statistics including charts data.
        """
        from django.db.models import Avg, Count, Q, Min, Max, F
        from collections import defaultdict

        project = self.get_object()

        # Get all properties across all lists
        all_properties = Property.objects.filter(
            property_lists__project=project
        ).distinct()

        # Basic stats
        price_stats = all_properties.aggregate(
            avg=Avg('price'),
            min=Min('price'),
            max=Max('price')
        )

        stats = {
            'total_properties': all_properties.count(),
            'avg_price': price_stats['avg'],
            'min_price': price_stats['min'],
            'max_price': price_stats['max'],
            'property_lists_count': project.property_lists.count(),
        }

        # Area breakdown
        stats['by_area'] = self._calculate_area_breakdown(project, all_properties)

        # Price distribution
        stats['price_distribution'] = self._calculate_price_distribution(all_properties)

        # Property types (extract from titles)
        stats['property_types'] = self._calculate_property_types(all_properties)

        # Ratings breakdown
        stats['ratings'] = self._calculate_ratings_breakdown(all_properties)

        # Property lists breakdown
        stats['by_property_list'] = self._calculate_lists_breakdown(project)

        return Response(stats)

    def _calculate_area_breakdown(self, project, all_properties):
        """Calculate statistics grouped by area"""
        from collections import defaultdict

        area_data = defaultdict(lambda: {'property_count': 0, 'prices': [], 'list_ids': set()})

        # Get property lists with their areas
        property_lists = project.property_lists.select_related('search_criteria').all()

        for prop_list in property_lists:
            area = prop_list.search_criteria.area if hasattr(prop_list, 'search_criteria') and prop_list.search_criteria else 'Unknown'
            area_data[area]['list_ids'].add(prop_list.uuid)

            # Get properties for this list
            props = all_properties.filter(property_lists=prop_list)
            for prop in props:
                if prop.uuid not in [p.get('id') for p in area_data[area].get('seen_props', [])]:
                    area_data[area]['property_count'] += 1
                    area_data[area]['prices'].append(prop.price)
                    area_data[area].setdefault('seen_props', []).append({'id': prop.uuid})

        # Format output
        result = []
        for area, data in area_data.items():
            avg_price = sum(data['prices']) / len(data['prices']) if data['prices'] else 0
            result.append({
                'name': area,
                'list_count': len(data['list_ids']),
                'property_count': data['property_count'],
                'avg_price': round(avg_price, 2)
            })

        return sorted(result, key=lambda x: x['property_count'], reverse=True)

    def _calculate_price_distribution(self, properties):
        """Calculate property count by price buckets"""
        buckets = [
            (0, 999, '£0-£999'),
            (1000, 1299, '£1000-£1299'),
            (1300, 1599, '£1300-£1599'),
            (1600, 1899, '£1600-£1899'),
            (1900, 2199, '£1900-£2199'),
            (2200, 2499, '£2200-£2499'),
            (2500, 2799, '£2500-£2799'),
            (2800, 2999, '£2800-£2999'),
            (3000, 1000000, '£3000+'),
        ]

        distribution = []
        for min_price, max_price, label in buckets:
            count = properties.filter(price__gte=min_price, price__lt=max_price).count()
            if count > 0:
                distribution.append({'range': label, 'count': count})

        return distribution

    def _calculate_property_types(self, properties):
        """Extract property types from titles"""
        from collections import Counter

        type_keywords = {
            'flat': ['flat', 'apartment'],
            'house': ['house', 'detached', 'semi-detached', 'terraced'],
            'bungalow': ['bungalow'],
            'maisonette': ['maisonette'],
            'studio': ['studio'],
        }

        type_counts = Counter()

        for prop in properties:
            title_lower = prop.title.lower()
            found = False
            for type_name, keywords in type_keywords.items():
                if any(kw in title_lower for kw in keywords):
                    type_counts[type_name] += 1
                    found = True
                    break
            if not found:
                type_counts['other'] += 1

        return [{'type': type_name.capitalize(), 'count': count}
                for type_name, count in type_counts.most_common()]

    def _calculate_ratings_breakdown(self, properties):
        """Calculate ratings statistics"""
        rated_props = properties.exclude(overall_rating__isnull=True)

        if not rated_props.exists():
            return {
                'total_rated': 0,
                'avg_rating': None,
                'rating_distribution': [],
                'disqualified_count': 0,
                'top_rated': []
            }

        # Rating distribution buckets
        buckets = [
            (0, 20, '0-20'),
            (21, 40, '21-40'),
            (41, 60, '41-60'),
            (61, 80, '61-80'),
            (81, 100, '81-100'),
        ]

        distribution = []
        for min_rating, max_rating, label in buckets:
            count = rated_props.filter(
                overall_rating__gte=min_rating,
                overall_rating__lte=max_rating
            ).count()
            distribution.append({'range': label, 'count': count})

        # Top rated (top 5)
        top_rated = rated_props.filter(disqualified=False).order_by('-overall_rating')[:5]
        top_rated_list = [
            {
                'uuid': str(prop.uuid),
                'title': prop.title,
                'rating': prop.overall_rating
            }
            for prop in top_rated
        ]

        return {
            'total_rated': rated_props.count(),
            'avg_rating': round(rated_props.aggregate(Avg('overall_rating'))['overall_rating__avg'], 2),
            'rating_distribution': distribution,
            'disqualified_count': rated_props.filter(disqualified=True).count(),
            'top_rated': top_rated_list
        }

    def _calculate_lists_breakdown(self, project):
        """Calculate statistics by property list"""
        from django.db.models import Avg, Count, Q

        result = []
        for prop_list in project.property_lists.all():
            properties = Property.objects.filter(property_lists=prop_list)

            price_avg = properties.aggregate(Avg('price'))['price__avg']
            rating_avg = properties.exclude(overall_rating__isnull=True).aggregate(
                Avg('overall_rating')
            )['overall_rating__avg']

            result.append({
                'uuid': str(prop_list.uuid),
                'title': prop_list.title,
                'property_count': properties.count(),
                'avg_price': round(price_avg, 2) if price_avg else None,
                'avg_rating': round(rating_avg, 2) if rating_avg else None,
                'stage2_complete': properties.filter(
                    Q(state='STAGE2_COMPLETE') | Q(state='STAGE3_IN_PROGRESS') | Q(state='STAGE3_COMPLETE')
                ).count(),
                'stage3_complete': properties.filter(state='STAGE3_COMPLETE').count(),
            })

        return sorted(result, key=lambda x: x['property_count'], reverse=True)

    @action(detail=True, methods=['get', 'put', 'patch'], url_path='rating-criteria')
    def rating_criteria_config(self, request, uuid=None):
        """
        GET /api/projects/{uuid}/rating-criteria/
        PUT/PATCH /api/projects/{uuid}/rating-criteria/

        Get or set rating criteria for project.
        """
        project = self.get_object()

        if request.method == 'GET':
            if not project.rating_criteria:
                return Response({
                    'rating_criteria': None,
                    'rating_criteria_name': None,
                    'is_configured': False
                })

            serializer = RatingCriteriaSerializer(project.rating_criteria)
            return Response({
                'rating_criteria': serializer.data,
                'rating_criteria_name': project.rating_criteria.name,
                'is_configured': True
            })

        # PUT/PATCH - Set rating criteria
        if not check_project_contributor(request.user, project):
            return Response(
                {'error': 'Only owners and contributors can update rating criteria.'},
                status=status.HTTP_403_FORBIDDEN
            )

        rating_criteria_uuid = request.data.get('rating_criteria_uuid')

        if not rating_criteria_uuid:
            return Response(
                {'error': 'rating_criteria_uuid is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            rating_criteria = RatingCriteria.objects.get(
                uuid=rating_criteria_uuid,
                owner=request.user
            )
        except RatingCriteria.DoesNotExist:
            return Response(
                {'error': 'Rating criteria not found or you do not have access'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if criteria is being shared (copy-on-write decision)
        if request.data.get('force_copy', False) and project.rating_criteria:
            # Track source for provenance
            project.rating_criteria_source = project.rating_criteria

        project.rating_criteria = rating_criteria
        project.save()

        return Response({
            'status': 'success',
            'message': 'Rating criteria set successfully',
            'rating_criteria_uuid': str(rating_criteria.uuid),
            'rating_criteria_name': rating_criteria.name
        })

    @action(detail=True, methods=['post'], url_path='run-stage3-bulk')
    @require_project_contributor()
    def run_stage3_bulk(self, request, uuid=None):
        """
        POST /api/projects/{uuid}/run-stage3-bulk/

        Trigger rating calculation for all eligible properties in project.
        """
        project = self.get_object()

        if not project.rating_criteria:
            return Response(
                {'error': 'No rating criteria configured for project'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Queue bulk task
        bulk_calculate_project_ratings.delay(project.id)

        return Response({
            'status': 'bulk_rating_started',
            'message': 'Rating calculation queued for all properties in project'
        })

    @action(detail=True, methods=['get'], url_path='property-comparison')
    def property_comparison(self, request, uuid=None):
        """
        GET /api/projects/{uuid}/property-comparison/

        Get sorted comparison of all rated properties in project.
        """
        project = self.get_object()

        # Get all rated properties
        all_properties = Property.objects.filter(
            property_lists__project=project,
            state='STAGE3_COMPLETE'
        ).distinct().order_by('-overall_rating')

        # Optional filtering
        min_rating = request.query_params.get('min_rating')
        if min_rating:
            all_properties = all_properties.filter(overall_rating__gte=float(min_rating))

        exclude_disqualified = request.query_params.get('exclude_disqualified', 'false').lower() == 'true'
        if exclude_disqualified:
            all_properties = all_properties.filter(disqualified=False)

        serializer = PropertyComparisonSerializer(all_properties, many=True)

        return Response({
            'project_id': str(project.uuid),
            'project_name': project.title,
            'total_properties': all_properties.count(),
            'properties': serializer.data
        })

    @action(detail=True, methods=['get'], url_path='favorites')
    def favorites(self, request, uuid=None):
        """
        GET /api/property/projects/{uuid}/favorites/

        Get all favorited properties in this project for current user.
        """
        project = self.get_object()

        # Get user's favorited properties in this project
        favorites = PropertyFavorite.objects.filter(
            property__property_lists__project=project
        ).select_related('property').distinct()

        properties = [fav.property for fav in favorites]
        serializer = PropertySerializer(
            properties,
            many=True,
            context={'request': request}
        )

        return Response({
            'project_id': str(project.uuid),
            'project_name': project.title,
            'total_favorites': len(properties),
            'properties': serializer.data
        })

    @action(detail=True, methods=['get'], url_path='members')
    def members(self, request, uuid=None):
        """GET /api/property/projects/{uuid}/members/"""
        project = self.get_object()
        data = {
            'owner': {'email': project.owner.email, 'first_name': project.owner.first_name, 'last_name': project.owner.last_name},
            'viewers': [{'email': u.email, 'first_name': u.first_name, 'last_name': u.last_name} for u in project.viewers.all()],
            'contributors': [{'email': u.email, 'first_name': u.first_name, 'last_name': u.last_name} for u in project.contributors.all()],
        }
        return Response(ProjectMembersSerializer(data).data)

    @action(detail=True, methods=['get'], url_path='invitations')
    def invitations(self, request, uuid=None):
        """GET /api/property/projects/{uuid}/invitations/ — owner only"""
        project = self.get_object()
        if project.owner != request.user:
            return Response({'error': 'Only the project owner can view invitations.'}, status=status.HTTP_403_FORBIDDEN)
        qs = ProjectInvitation.objects.filter(project=project).order_by('-created_at')
        return Response(ProjectInvitationSerializer(qs, many=True).data)

    @action(detail=True, methods=['post'], url_path='invite')
    def invite(self, request, uuid=None):
        """POST /api/property/projects/{uuid}/invite/ — owner only"""
        project = self.get_object()
        if project.owner != request.user:
            return Response({'error': 'Only the project owner can send invitations.'}, status=status.HTTP_403_FORBIDDEN)

        invited_email = request.data.get('email', '').strip().lower()
        role = request.data.get('role', '')

        if not invited_email:
            return Response({'error': 'email is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if role not in ('viewer', 'contributor'):
            return Response({'error': 'role must be viewer or contributor.'}, status=status.HTTP_400_BAD_REQUEST)

        if project.owner.email.lower() == invited_email:
            return Response({'error': 'Cannot invite the project owner.'}, status=status.HTTP_400_BAD_REQUEST)

        if project.viewers.filter(email__iexact=invited_email).exists() or \
                project.contributors.filter(email__iexact=invited_email).exists():
            return Response({'error': 'User is already a member of this project.'}, status=status.HTTP_400_BAD_REQUEST)

        existing = ProjectInvitation.objects.filter(
            project=project, invited_email__iexact=invited_email, status='pending'
        ).first()

        if existing:
            existing_token = generate_invite_token(str(existing.uuid))
            existing_invite_url = f"{settings.FRONTEND_URL}/register?invite_token={existing_token}"
            return Response(ProjectInvitationSerializer(existing, context={'invite_url': existing_invite_url}).data, status=status.HTTP_200_OK)

        invitation_uuid = uuid4()
        token = generate_invite_token(str(invitation_uuid))
        token_hash_val = hash_token(token)
        invite_url = f"{settings.FRONTEND_URL}/register?invite_token={token}"

        invitation = ProjectInvitation.objects.create(
            uuid=invitation_uuid,
            project=project,
            invited_by=request.user,
            invited_email=invited_email,
            role=role,
            token_hash=token_hash_val,
            expires_at=timezone.now() + timezone.timedelta(days=7),
        )

        send_mail(
            subject=f"You've been invited to join {project.title} on Homely",
            message=(
                f"{request.user.first_name or request.user.email} has invited you to join "
                f"'{project.title}' as a {role}.\n\nAccept or decline here:\n{invite_url}\n\n"
                f"This link expires in 7 days."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invited_email],
            fail_silently=True,
        )

        try:
            invited_user = User.objects.get(email__iexact=invited_email)
            inviter_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email
            create_notification(
                recipient=invited_user,
                actor=request.user,
                notification_type='invite_received',
                title=f"Project invitation from {inviter_name}",
                message=f"{inviter_name} invited you to join '{project.title}' as a {role}.",
                related_object_uuid=project.uuid,
                related_object_type='project',
            )
        except User.DoesNotExist:
            pass

        serializer = ProjectInvitationSerializer(invitation, context={'invite_url': invite_url})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path=r'invitations/(?P<invitation_uuid>[^/.]+)')
    def revoke_invitation(self, request, uuid=None, invitation_uuid=None):
        """DELETE /api/property/projects/{uuid}/invitations/{invitation_uuid}/"""
        project = self.get_object()
        if project.owner != request.user:
            return Response({'error': 'Only the project owner can revoke invitations.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            invitation = ProjectInvitation.objects.get(uuid=invitation_uuid, project=project, status='pending')
        except ProjectInvitation.DoesNotExist:
            return Response({'error': 'Pending invitation not found.'}, status=status.HTTP_404_NOT_FOUND)
        invitation.status = 'revoked'
        invitation.save(update_fields=['status'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['delete'], url_path=r'members/(?P<member_email>[^/]+)')
    def remove_member(self, request, uuid=None, member_email=None):
        """DELETE /api/property/projects/{uuid}/members/{member_email}/"""
        project = self.get_object()
        if project.owner != request.user:
            return Response({'error': 'Only the project owner can remove members.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            user = User.objects.get(email__iexact=member_email)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        removed = False
        if project.viewers.filter(pk=user.pk).exists():
            project.viewers.remove(user)
            removed = True
        if project.contributors.filter(pk=user.pk).exists():
            project.contributors.remove(user)
            removed = True

        if not removed:
            return Response({'error': 'User is not a member of this project.'}, status=status.HTTP_400_BAD_REQUEST)

        owner_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email
        create_notification(
            recipient=user,
            actor=request.user,
            notification_type='member_removed',
            title=f"Removed from '{project.title}'",
            message=f"{owner_name} removed you from '{project.title}'.",
            related_object_uuid=project.uuid,
            related_object_type='project',
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'], url_path='my-invite')
    def my_invite(self, request):
        """GET /api/property/projects/my-invite/?project_uuid=... — returns token for current user's pending invite"""
        project_uuid = request.query_params.get('project_uuid', '')
        if not project_uuid:
            return Response({'error': 'project_uuid is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            invitation = ProjectInvitation.objects.get(
                project__uuid=project_uuid,
                invited_email__iexact=request.user.email,
                status='pending',
            )
        except ProjectInvitation.DoesNotExist:
            return Response({'error': 'No pending invitation found.'}, status=status.HTTP_404_NOT_FOUND)
        token = generate_invite_token(str(invitation.uuid))
        return Response({'token': token})

    @action(detail=False, methods=['get'], url_path='preview-invite', permission_classes=[AllowAny])
    def preview_invite(self, request):
        """GET /api/property/projects/preview-invite/?token=... — no auth required"""
        token = request.query_params.get('token', '')
        if not token:
            return Response({'error': 'token is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            invitation_uuid = verify_invite_token(token)
        except signing.SignatureExpired:
            return Response({'error': 'invalid_or_expired_token'}, status=status.HTTP_400_BAD_REQUEST)
        except signing.BadSignature:
            return Response({'error': 'invalid_or_expired_token'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            invitation = ProjectInvitation.objects.select_related('project', 'invited_by').get(
                uuid=invitation_uuid, status='pending'
            )
        except ProjectInvitation.DoesNotExist:
            return Response({'error': 'invitation_already_used'}, status=status.HTTP_400_BAD_REQUEST)

        inviter_name = f"{invitation.invited_by.first_name} {invitation.invited_by.last_name}".strip() or invitation.invited_by.email
        data = {
            'project_uuid': invitation.project.uuid,
            'project_title': invitation.project.title,
            'invited_by_name': inviter_name,
            'invited_by_email': invitation.invited_by.email,
            'role': invitation.role,
            'expires_at': invitation.expires_at,
        }
        return Response(InvitePreviewSerializer(data).data)

    @action(detail=False, methods=['post'], url_path='accept-invite')
    def accept_invite(self, request):
        """POST /api/property/projects/accept-invite/"""
        token = request.data.get('token', '')
        if not token:
            return Response({'error': 'token is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            invitation_uuid = verify_invite_token(token)
        except signing.SignatureExpired:
            return Response({'error': 'invalid_or_expired_token'}, status=status.HTTP_400_BAD_REQUEST)
        except signing.BadSignature:
            return Response({'error': 'invalid_or_expired_token'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            invitation = ProjectInvitation.objects.select_related('project', 'invited_by').get(
                uuid=invitation_uuid, status='pending'
            )
        except ProjectInvitation.DoesNotExist:
            return Response({'error': 'invitation_already_used'}, status=status.HTTP_400_BAD_REQUEST)

        if request.user.email.lower() != invitation.invited_email.lower():
            return Response({'error': 'email_mismatch', 'detail': 'This invitation was sent to a different email address.'}, status=status.HTTP_403_FORBIDDEN)

        project = invitation.project
        if invitation.role == 'viewer':
            project.viewers.add(request.user)
        else:
            project.contributors.add(request.user)

        invitation.status = 'accepted'
        invitation.accepted_by = request.user
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=['status', 'accepted_by', 'accepted_at'])

        acceptor_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email
        create_notification(
            recipient=project.owner,
            actor=request.user,
            notification_type='invite_accepted',
            title=f"{acceptor_name} joined '{project.title}'",
            message=f"{acceptor_name} accepted your invitation to join '{project.title}' as a {invitation.role}.",
            related_object_uuid=project.uuid,
            related_object_type='project',
        )
        return Response({'project_uuid': str(project.uuid), 'role': invitation.role})

    @action(detail=False, methods=['post'], url_path='decline-invite')
    def decline_invite(self, request):
        """POST /api/property/projects/decline-invite/"""
        token = request.data.get('token', '')
        if not token:
            return Response({'error': 'token is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            invitation_uuid = verify_invite_token(token)
        except signing.SignatureExpired:
            return Response({'error': 'invalid_or_expired_token'}, status=status.HTTP_400_BAD_REQUEST)
        except signing.BadSignature:
            return Response({'error': 'invalid_or_expired_token'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            invitation = ProjectInvitation.objects.select_related('project', 'invited_by').get(
                uuid=invitation_uuid, status='pending'
            )
        except ProjectInvitation.DoesNotExist:
            return Response({'error': 'invitation_already_used'}, status=status.HTTP_400_BAD_REQUEST)

        if request.user.email.lower() != invitation.invited_email.lower():
            return Response({'error': 'email_mismatch', 'detail': 'This invitation was sent to a different email address.'}, status=status.HTTP_403_FORBIDDEN)

        invitation.status = 'declined'
        invitation.save(update_fields=['status'])

        decliner_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email
        create_notification(
            recipient=invitation.invited_by,
            actor=request.user,
            notification_type='invite_declined',
            title=f"{decliner_name} declined your invitation",
            message=f"{decliner_name} declined your invitation to join '{invitation.project.title}'.",
            related_object_uuid=invitation.project.uuid,
            related_object_type='project',
        )
        return Response({'detail': 'Invitation declined.'})

    @action(detail=True, methods=['get'], url_path='user-role')
    def user_role(self, request, uuid=None):
        """GET /api/property/projects/{uuid}/user-role/ - returns user's role in project"""
        project = self.get_object()
        user = request.user

        if project.owner == user:
            return Response({'role': 'owner'})
        elif project.contributors.filter(pk=user.pk).exists():
            return Response({'role': 'contributor'})
        elif project.viewers.filter(pk=user.pk).exists():
            return Response({'role': 'viewer'})
        else:
            return Response({'role': None})


class NotificationViewSet(viewsets.GenericViewSet):
    """ViewSet for in-app notifications."""
    permission_classes = [IsAuthenticated]
    serializer_class = AppNotificationSerializer
    lookup_field = 'uuid'

    def get_queryset(self):
        return AppNotification.objects.filter(recipient=self.request.user)

    def list(self, request):
        """GET /api/property/notifications/"""
        qs = self.get_queryset()
        return Response(AppNotificationSerializer(qs, many=True).data)

    @action(detail=True, methods=['post'], url_path='read')
    def mark_read(self, request, uuid=None):
        """POST /api/property/notifications/{uuid}/read/"""
        try:
            notification = self.get_queryset().get(uuid=uuid)
        except AppNotification.DoesNotExist:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response(AppNotificationSerializer(notification).data)

    @action(detail=False, methods=['post'], url_path='read-all')
    def mark_all_read(self, request):
        """POST /api/property/notifications/read-all/"""
        self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({'detail': 'All notifications marked as read.'})

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        """GET /api/property/notifications/unread-count/"""
        count = self.get_queryset().filter(is_read=False).count()
        return Response({'count': count})


class TaskListViewSet(viewsets.ModelViewSet):
    """
    ViewSet for TaskList CRUD operations.
    Users can access task lists for projects they have access to.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = TaskListSerializer
    lookup_field = 'uuid'

    def get_queryset(self):
        """Filter to task lists in accessible projects"""
        user = self.request.user
        return TaskList.objects.filter(
            Q(project__owner=user) |
            Q(project__viewers=user) |
            Q(project__contributors=user)
        ).distinct()


class TaskViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Task CRUD operations.
    Users can access tasks in task lists they have access to.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = TaskSerializer
    lookup_field = 'uuid'

    def get_queryset(self):
        """Filter to tasks in accessible task lists"""
        user = self.request.user
        return Task.objects.filter(
            Q(task_list__project__owner=user) |
            Q(task_list__project__viewers=user) |
            Q(task_list__project__contributors=user)
        ).distinct()


class PropertyListViewSet(viewsets.ModelViewSet):
    """
    ViewSet for PropertyList CRUD operations.

    Users can access property lists in projects they own, view, or contribute to.
    Lookup by UUID for public-facing URLs.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = PropertyListSerializer
    lookup_field = 'uuid'

    def get_queryset(self):
        """Filter to lists in accessible projects"""
        user = self.request.user
        queryset = PropertyList.objects.filter(
            Q(project__owner=user) |
            Q(project__viewers=user) |
            Q(project__contributors=user)
        ).distinct()

        # Optional filter by project uuid
        project_uuid = self.request.query_params.get('project')
        if project_uuid:
            queryset = queryset.filter(project__uuid=project_uuid)

        return queryset

    def get_serializer_class(self):
        """Use detailed serializer for retrieve action"""
        if self.action == 'retrieve':
            return PropertyListDetailSerializer
        return PropertyListSerializer

    @require_project_contributor()
    def update(self, request, *args, **kwargs):
        """Update property list - owner or contributor only"""
        return super().update(request, *args, **kwargs)

    @require_project_contributor()
    def partial_update(self, request, *args, **kwargs):
        """Partial update property list - owner or contributor only"""
        return super().partial_update(request, *args, **kwargs)

    @require_project_contributor()
    def destroy(self, request, *args, **kwargs):
        """Delete property list - owner or contributor only"""
        return super().destroy(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        """
        POST /api/property/property-lists/

        Create PropertyList with auto-scraping.
        """
        from property.utils.rightmove_validation import validate_rightmove_area, get_area_suggestions
        from property.utils.title_generation import generate_unique_list_title

        # Extract data
        project_uuid = request.data.get('project_uuid')
        search_criteria_data = request.data.get('search_criteria')

        if not project_uuid or not search_criteria_data:
            return Response({
                'error': 'project_uuid and search_criteria are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get project
        try:
            project = Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            return Response({
                'error': f'Project {project_uuid} not found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Validate user has access to project
        if not check_project_contributor(request.user, project):
            return Response({
                'error': 'You do not have permission to add lists to this project'
            }, status=status.HTTP_403_FORBIDDEN)

        # Validate Rightmove area
        area = search_criteria_data.get('area')
        if not area:
            return Response({
                'error': 'area is required in search_criteria'
            }, status=status.HTTP_400_BAD_REQUEST)

        is_valid, error_msg = validate_rightmove_area(area)

        if not is_valid:
            suggestions = get_area_suggestions(area)
            return Response({
                'error': error_msg,
                'suggestions': suggestions
            }, status=status.HTTP_400_BAD_REQUEST)

        # Generate unique title
        title = generate_unique_list_title(area, project)

        # Create SearchCriteria
        search_criteria = SearchCriteria.objects.create(**search_criteria_data)

        # Create PropertyList
        property_list = PropertyList.objects.create(
            owner=request.user,
            project=project,
            title=title,
            search_criteria=search_criteria
        )

        # Create PropertyListTask for tracking
        task_obj = PropertyListTask.objects.create(
            property_list=property_list,
            task_type='SCRAPE_SEARCH',
            status='QUEUED'
        )

        # Trigger async scraping
        max_properties = request.data.get('max_properties', 100)
        transaction.on_commit(
            lambda: scrape_rightmove_properties.delay(str(task_obj.uuid), max_properties=max_properties)
        )

        # Serialize response
        serializer = self.get_serializer(property_list)

        return Response({
            **serializer.data,
            'scraping_task_uuid': str(task_obj.uuid),
            'scraping_status': 'QUEUED'
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='run-stage2-bulk')
    def run_stage2_bulk(self, request, uuid=None):
        """
        POST /api/property/property-lists/{uuid}/run-stage2-bulk/

        Run Stage 2 on all properties in this list.
        """
        from property.tasks import bulk_retrieve_context_data

        property_list = self.get_object()

        # Check if project has context options
        if not hasattr(property_list.project, 'context_options'):
            return Response({
                'error': 'Project has no context options configured',
                'action_required': 'configure_context_options'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get eligible properties
        eligible_properties = property_list.properties.filter(
            state__in=['NEW', 'STAGE2_COMPLETE']
        )

        if not eligible_properties.exists():
            return Response({
                'message': 'No properties eligible for Stage 2',
                'eligible_count': 0
            })

        # Queue bulk task
        property_ids = list(eligible_properties.values_list('id', flat=True))
        bulk_retrieve_context_data.delay(property_ids, property_list.id)

        return Response({
            'status': 'bulk_stage2_queued',
            'property_count': len(property_ids),
            'message': f'Stage 2 queued for {len(property_ids)} properties'
        })

    @action(detail=True, methods=['post'], url_path='run-stage3-bulk')
    def run_stage3_bulk(self, request, uuid=None):
        """
        POST /api/property/property-lists/{uuid}/run-stage3-bulk/

        Run Stage 3 on all properties in this list.
        """
        from property.tasks import bulk_calculate_ratings

        property_list = self.get_object()

        # Check if project has rating criteria
        if not property_list.project.rating_criteria:
            return Response({
                'error': 'Project has no rating criteria configured',
                'action_required': 'configure_rating_criteria'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get eligible properties
        eligible_properties = property_list.properties.filter(
            state='STAGE2_COMPLETE'
        )

        if not eligible_properties.exists():
            return Response({
                'message': 'No properties eligible for Stage 3',
                'eligible_count': 0
            })

        # Queue bulk task
        property_ids = list(eligible_properties.values_list('id', flat=True))
        rating_criteria_id = property_list.project.rating_criteria.id
        bulk_calculate_ratings.delay(property_ids, rating_criteria_id)

        return Response({
            'status': 'bulk_stage3_queued',
            'property_count': len(property_ids),
            'message': f'Stage 3 queued for {len(property_ids)} properties'
        })

    @extend_schema(
        request=BulkPropertyCreationSerializer,
        responses={
            202: PropertyListTaskSerializer,
            400: OpenApiResponse(description="Invalid search criteria"),
        },
        description="Start bulk property scraping from Rightmove search criteria. Returns task details for tracking progress."
    )
    @action(detail=True, methods=['post'], url_path='create-from-search')
    @transaction.atomic
    def create_from_search(self, request, uuid=None):
        property_list = self.get_object()
        logger.debug("create_from_search requested for property_list=%s by user=%s", uuid, request.user.id)

        serializer = BulkPropertyCreationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        search_criteria_data = serializer.validated_data['search_criteria']
        max_properties = serializer.validated_data.get('max_properties', 100)
        logger.debug("create_from_search criteria=%s max_properties=%d", search_criteria_data, max_properties)

        if property_list.search_criteria:
            search_criteria = property_list.search_criteria
            for field, value in search_criteria_data.items():
                setattr(search_criteria, field, value)
            search_criteria.save()
            logger.debug("create_from_search updated existing search_criteria=%s", search_criteria.id)
        else:
            search_criteria = SearchCriteria.objects.create(**search_criteria_data)
            property_list.search_criteria = search_criteria
            property_list.save()
            logger.debug("create_from_search created new search_criteria=%s", search_criteria.id)

        task = PropertyListTask.objects.create(
            property_list=property_list,
            task_type='SCRAPE_SEARCH',
            status='QUEUED'
        )

        transaction.on_commit(
            lambda: scrape_rightmove_properties.delay(str(task.uuid), max_properties=max_properties)
        )
        logger.debug("create_from_search queued task=%s", task.uuid)

        task_serializer = PropertyListTaskSerializer(task, context={'request': request})
        return Response(task_serializer.data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(
        responses={
            200: PropertyListTaskSerializer,
            404: OpenApiResponse(description="Task not found"),
        },
        description="Get status of a scraping task. Polling fallback for clients without websocket support."
    )
    @action(detail=True, methods=['get'], url_path='scrape-status/(?P<task_uuid>[^/.]+)')
    def scrape_status(self, request, uuid=None, task_uuid=None):
        """
        Get scraping task status.

        Polling endpoint for progress updates (fallback for no websocket).
        Returns current task status, progress, and errors.
        """
        property_list = self.get_object()

        try:
            task = PropertyListTask.objects.get(
                uuid=task_uuid,
                property_list=property_list
            )

            serializer = PropertyListTaskSerializer(task, context={'request': request})
            return Response(serializer.data)

        except PropertyListTask.DoesNotExist:
            return Response(
                {'error': f'Task {task_uuid} not found for this property list'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['get', 'put', 'patch'], url_path='context-options')
    def context_options(self, request, uuid=None):
        """Get or update context options for a property list"""
        property_list = self.get_object()
        context_options_obj, _ = ContextOptions.objects.get_or_create(property_list=property_list)

        if request.method == 'GET':
            serializer = ContextOptionsSerializer(context_options_obj)
            return Response(serializer.data)

        partial = request.method == 'PATCH'
        serializer = ContextOptionsSerializer(context_options_obj, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PropertyViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Property CRUD operations.

    Users can only access properties in their own lists.
    Lookup by UUID for public-facing URLs.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = PropertySerializer
    lookup_field = 'uuid'

    def get_queryset(self):
        """Filter to properties in accessible projects"""
        user = self.request.user
        queryset = Property.objects.filter(
            Q(property_lists__project__owner=user) |
            Q(property_lists__project__viewers=user) |
            Q(property_lists__project__contributors=user)
        ).distinct()

        # Optional filter by property_list uuid
        property_list_uuid = self.request.query_params.get('property_list')
        if property_list_uuid:
            queryset = queryset.filter(property_lists__uuid=property_list_uuid)

        return queryset

    def get_serializer_class(self):
        """Use detailed serializer for retrieve action"""
        if self.action == 'retrieve':
            return PropertyDetailSerializer
        return PropertySerializer

    @require_project_contributor()
    def update(self, request, *args, **kwargs):
        """Update property - owner or contributor only"""
        return super().update(request, *args, **kwargs)

    @require_project_contributor()
    def partial_update(self, request, *args, **kwargs):
        """Partial update property - owner or contributor only"""
        return super().partial_update(request, *args, **kwargs)

    @require_project_contributor()
    def destroy(self, request, *args, **kwargs):
        """Delete property - owner or contributor only"""
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='run-stage2')
    @require_project_contributor()
    def run_stage2(self, request, uuid=None):
        """Trigger Stage 2 context retrieval (NEW → STAGE2_IN_PROGRESS)

        Optional body: { "services": ["crime", "schools"] } to run specific services
        """
        property_obj = self.get_object()
        services = request.data.get('services', None)

        try:
            property_obj.run_stage2()
            property_obj.save()

            # Queue Celery task (uses internal id)
            retrieve_context_data.delay(property_obj.id, services=services)

            return Response({
                'status': 'stage2_started',
                'state': property_obj.state,
                'message': 'Context data retrieval queued'
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    @require_project_contributor()
    def run_stage3(self, request, uuid=None):
        """Trigger Stage 3 rating calculation (STAGE2_COMPLETE → STAGE3_IN_PROGRESS)"""
        property_obj = self.get_object()

        try:
            property_obj.run_stage3()
            property_obj.save()

            # Queue Celery task (uses internal id)
            calculate_property_rating.delay(property_obj.id)

            return Response({
                'status': 'stage3_started',
                'state': property_obj.state,
                'message': 'Rating calculation queued'
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    @require_project_contributor()
    def rerun_services(self, request, uuid=None):
        """Rerun context services (STAGE2_COMPLETE/STAGE3_* → STAGE2_IN_PROGRESS)"""
        property_obj = self.get_object()

        try:
            property_obj.rerun_services()
            property_obj.save()

            # Queue Celery task (uses internal id)
            retrieve_context_data.delay(property_obj.id)

            return Response({
                'status': 'services_rerun_started',
                'state': property_obj.state,
                'message': 'Context services rerun queued'
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['get'], url_path='context-data')
    def context_data(self, request, uuid=None):
        """Get all context data for a property"""
        from property.utils.report_transformers import transform_context_data

        property_obj = self.get_object()
        context_data = ContextData.objects.filter(property=property_obj)

        data = []
        for cd in context_data:
            # Transform service data to match frontend expectations
            transformed_data = None
            if cd.status == 'COMPLETE' and cd.data:
                transformed_data = transform_context_data(cd.service_name, cd.data)

            data.append({
                'id': str(cd.uuid),
                'property_id': str(property_obj.uuid),
                'service_name': cd.service_name,
                'status': cd.status,
                'data': transformed_data,
                'error_message': cd.error_message,
                'started_at': cd.last_attempt_at,
                'completed_at': cd.completed_at,
                'cached': False
            })

        return Response(data)

    @action(detail=True, methods=['get'], url_path='context-data/(?P<service_name>[^/.]+)')
    def context_data_detail(self, request, uuid=None, service_name=None):
        """Get specific service context data for a property"""

        property_obj = self.get_object()

        try:
            context_data = ContextData.objects.get(
                property=property_obj,
                service_name=service_name
            )

            return Response({
                'service_name': context_data.service_name,
                'status': context_data.status,
                'data': context_data.data,
                'error_message': context_data.error_message,
                'error_type': context_data.error_type,
                'retry_count': context_data.retry_count,
                'completed_at': context_data.completed_at,
                'last_attempt_at': context_data.last_attempt_at
            })
        except ContextData.DoesNotExist:
            return Response(
                {'error': f'No context data found for service {service_name}'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['post'], url_path='retry-service/(?P<service_name>[^/.]+)')
    def retry_service(self, request, uuid=None, service_name=None):
        """Retry a failed context service"""
        from property.tasks import run_service_task

        property_obj = self.get_object()

        try:
            context_data = ContextData.objects.get(
                property=property_obj,
                service_name=service_name
            )

            if context_data.status not in ['FAILED', 'COMPLETE']:
                return Response(
                    {'error': f'Service {service_name} is currently {context_data.status}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Reset to PENDING and queue task
            context_data.status = 'PENDING'
            context_data.error_message = ''
            context_data.error_type = ''
            context_data.save()

            run_service_task.delay(property_obj.id, service_name)

            return Response({
                'status': 'service_retry_queued',
                'service_name': service_name,
                'message': f'Service {service_name} queued for retry'
            })

        except ContextData.DoesNotExist:
            return Response(
                {'error': f'No context data found for service {service_name}'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['get'], url_path='rating')
    def rating(self, request, uuid=None):
        """
        GET /api/properties/{uuid}/rating/

        Get overall rating and breakdown for a property.
        """
        property_obj = self.get_object()

        if property_obj.state not in ['STAGE3_COMPLETE']:
            return Response(
                {'error': 'Property rating not yet calculated'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = PropertyRatingSerializer(property_obj)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='criterion-scores')
    def criterion_scores(self, request, uuid=None):
        """
        GET /api/properties/{uuid}/criterion-scores/

        Get detailed criterion scores for a property.
        """
        property_obj = self.get_object()

        if property_obj.state not in ['STAGE3_COMPLETE']:
            return Response(
                {'error': 'Property rating not yet calculated'},
                status=status.HTTP_400_BAD_REQUEST
            )

        criterion_scores = CriterionScore.objects.filter(property=property_obj).select_related('criterion')
        serializer = CriterionScoreSerializer(criterion_scores, many=True)

        return Response({
            'property_id': str(property_obj.uuid),
            'overall_rating': float(property_obj.overall_rating) if property_obj.overall_rating else None,
            'criterion_scores': serializer.data
        })

    @action(detail=True, methods=['get'], url_path='broadband')
    def broadband(self, request, uuid=None):
        """Get broadband coverage data for property"""
        from property.services.context_retrieval.broadband_dataset_service import BroadbandDatasetService

        property_obj = self.get_object()

        # Try to get from context data first
        try:
            context_data = ContextData.objects.get(
                property=property_obj,
                service_name='broadband'
            )

            if context_data.status == 'COMPLETE':
                return Response(context_data.data)
            elif context_data.status == 'FAILED':
                return Response(
                    {
                        'error': 'Failed to fetch broadband data',
                        'message': context_data.error_message
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            else:
                return Response(
                    {
                        'status': context_data.status,
                        'message': 'Broadband data is being fetched'
                    },
                    status=status.HTTP_202_ACCEPTED
                )

        except ContextData.DoesNotExist:
            # Fetch on-demand if not in context data
            try:
                service = BroadbandDatasetService()
                data = service.fetch_data(property_obj)
                return Response(data)
            except Exception as e:
                return Response(
                    {'error': f'Failed to fetch broadband data: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

    @action(detail=True, methods=['get'], url_path='mobile')
    def mobile(self, request, uuid=None):
        """Get mobile coverage data for property"""
        from property.services.context_retrieval.mobile_dataset_service import MobileDatasetService

        property_obj = self.get_object()

        # Try to get from context data first
        try:
            context_data = ContextData.objects.get(
                property=property_obj,
                service_name='mobile'
            )

            if context_data.status == 'COMPLETE':
                return Response(context_data.data)
            elif context_data.status == 'FAILED':
                return Response(
                    {
                        'error': 'Failed to fetch mobile data',
                        'message': context_data.error_message
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            else:
                return Response(
                    {
                        'status': context_data.status,
                        'message': 'Mobile data is being fetched'
                    },
                    status=status.HTTP_202_ACCEPTED
                )

        except ContextData.DoesNotExist:
            # Fetch on-demand if not in context data
            try:
                service = MobileDatasetService()
                data = service.fetch_data(property_obj)
                return Response(data)
            except Exception as e:
                return Response(
                    {'error': f'Failed to fetch mobile data: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

    @action(detail=True, methods=['get'], url_path='places-of-interest')
    def places_of_interest(self, request, uuid=None):
        """
        Get Places of Interest for property.

        Optional query param:
        - place_type: Filter by specific type (e.g., 'school', 'hospital')
        """

        property_obj = self.get_object()
        place_type = request.query_params.get('place_type')

        # Query POIs for this property
        pois = PlaceOfInterest.objects.filter(property=property_obj)

        # Filter by type if specified
        if place_type:
            pois = pois.filter(place_type=place_type)

        # Order by distance
        pois = pois.order_by('place_type', 'straight_distance_km')

        serializer = PlaceOfInterestSerializer(pois, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=CreateFromInputSerializer,
        responses={
            200: OpenApiResponse(
                description="Property data extracted successfully",
                examples=[
                    OpenApiExample(
                        'Success Response',
                        value={
                            "success": True,
                            "property_data": {
                                "title": "3 bedroom house in London",
                                "price": "500000.00",
                                "address_line_1": "123 Example Street",
                                "city": "London",
                                "postcode": "SW1A 1AA",
                                "bedrooms": 3,
                                "bathrooms": 2,
                                "garden": True,
                                "parking": False,
                                "external_url": "https://www.rightmove.co.uk/properties/123456",
                                "external_id": "123456"
                            },
                            "source": "RightmoveService",
                            "message": "Property data extracted successfully"
                        }
                    )
                ]
            ),
            201: PropertySerializer,
            400: OpenApiResponse(description="Invalid input or extraction failed"),
        },
        description="Extract property data from URL or text input. Optionally create Property model if property_list_uuid provided."
    )
    @action(detail=False, methods=['post'], url_path='create-from-input')
    def create_from_input(self, request):
        """
        Extract property data from URL or text input.

        If property_list_uuid is provided, creates Property model and adds to list.
        Otherwise, returns unsaved property data that can be used to populate form.
        """
        # Validate input using serializer
        serializer = CreateFromInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        input_data = serializer.validated_data['input_data']
        input_type = serializer.validated_data['input_type']
        property_list_uuid = request.data.get('property_list_uuid')

        # Validate property_list access BEFORE extracting data
        property_list = None
        if property_list_uuid:
            try:
                property_list = PropertyList.objects.get(uuid=property_list_uuid)
                project = property_list.project
                if not check_project_contributor(request.user, project):
                    return Response(
                        {'error': 'Property list not found or access denied'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            except PropertyList.DoesNotExist:
                return Response(
                    {'error': 'Property list not found or access denied'},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Get appropriate service
        service = property_creation_service_factory(input_data, input_type)

        if not service:
            return Response(
                {
                    'error': 'No service available to handle this input',
                    'message': f'Could not find a service to process this {input_type}'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Extract property data
        try:
            # If property_list provided, create Property model using service
            if property_list:
                property_obj, created = service.create_property(input_data, input_type, property_list)

                property_serializer = PropertySerializer(property_obj, context={'request': request})

                if created:
                    return Response({
                        'success': True,
                        'property': property_serializer.data,
                        'created': True,
                        'message': 'Property created successfully',
                        'source': service.__class__.__name__
                    }, status=status.HTTP_201_CREATED)
                else:
                    return Response({
                        'success': True,
                        'property': property_serializer.data,
                        'created': False,
                        'updated': True,
                        'message': 'Property already exists, added to list and updated with latest data',
                        'source': service.__class__.__name__
                    })

            # No property_list_uuid, just extract and return data
            property_data = service.extract_property_data(input_data, input_type)
            return Response({
                'success': True,
                'property_data': property_data,
                'source': service.__class__.__name__,
                'message': 'Property data extracted successfully'
            })

        except ValueError as e:
            return Response(
                {
                    'error': 'Extraction failed',
                    'message': str(e)
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {
                    'error': 'Unexpected error',
                    'message': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



class SavedLocationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for SavedLocation CRUD operations.

    Users can only access their own saved locations.
    Lookup by UUID for public-facing URLs.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = SavedLocationSerializer
    lookup_field = 'uuid'

    def get_queryset(self):
        """Filter to user's own saved locations"""
        return SavedLocation.objects.filter(user=self.request.user)


class SchoolViewSet(viewsets.ViewSet):
    """
    ViewSet for school-related operations.

    Provides endpoints for retrieving Ofsted reports.
    """
    permission_classes = [IsAuthenticated]

    def ofsted_report(self, request, urn=None):
        """
        Get Ofsted report for a school by URN.

        Returns cached data if available (30 days TTL).

        Example:
            GET /api/schools/ofsted/100000/
        """
        from property.services.context_retrieval.ofsted_service import OfstedService

        if not urn:
            return Response(
                {'error': 'URN is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Fetch Ofsted data
        data = OfstedService.get_ofsted_report(urn)

        # Check if error
        if 'error' in data:
            if data['error'] == 'School not found':
                return Response(data, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response(data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(data, status=status.HTTP_200_OK)


class RatingCriteriaViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Rating Criteria CRUD operations.

    Users can only access their own rating criteria.
    Lookup by UUID for public-facing URLs.
    """
    permission_classes = [IsAuthenticated]
    lookup_field = 'uuid'

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return RatingCriteriaCreateSerializer
        return RatingCriteriaSerializer

    def get_queryset(self):
        """Filter to user's own rating criteria"""
        return RatingCriteria.objects.filter(owner=self.request.user).prefetch_related('criteria')

    def perform_create(self, serializer):
        """Set owner to current user"""
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=['post'], url_path='copy')
    def copy(self, request, uuid=None):
        """
        POST /api/rating-criteria/{uuid}/copy/

        Create a copy of rating criteria.
        Used when user wants to modify shared criteria (copy-on-write).
        """
        source_criteria = self.get_object()

        # Create new criteria
        new_criteria = RatingCriteria.objects.create(
            owner=request.user,
            name=f"{source_criteria.name} (Copy)"
        )

        # Copy all criteria
        for criterion in source_criteria.criteria.all():
            Criterion.objects.create(
                rating_criteria=new_criteria,
                name=criterion.name,
                source=criterion.source,
                field_name=criterion.field_name,
                saved_location_uuid=criterion.saved_location_uuid,
                poi_category=criterion.poi_category,
                weight=criterion.weight
            )

        serializer = RatingCriteriaSerializer(new_criteria)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PropertyFavoriteViewSet(viewsets.ViewSet):
    """
    ViewSet for Property Favorites.
    Users can favorite/unfavorite properties and list their favorites.
    """
    permission_classes = [IsAuthenticated]

    def list(self, request):
        """
        GET /api/property/favorites/

        List all properties user has favorited (across all accessible projects).
        """
        # Get user's accessible projects
        accessible_projects = Project.objects.filter(
            Q(owner=request.user) | Q(viewers=request.user) | Q(contributors=request.user)
        ).distinct()

        # Get favorited properties that belong to accessible projects
        favorites = PropertyFavorite.objects.filter(
            user=request.user,
            property__property_lists__project__in=accessible_projects
        ).select_related('property').distinct()

        # Serialize properties with project info
        properties = [fav.property for fav in favorites]
        serializer = PropertySerializer(
            properties,
            many=True,
            context={'request': request}
        )

        return Response(serializer.data)

    def create(self, request):
        """
        POST /api/property/favorites/
        Body: {"property_uuid": "<uuid>"}

        Add property to user's favorites.
        """
        property_uuid = request.data.get('property_uuid')

        if not property_uuid:
            return Response(
                {'error': 'property_uuid is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            property_obj = Property.objects.get(uuid=property_uuid)
        except Property.DoesNotExist:
            return Response(
                {'error': 'Property not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check user has access to at least one project containing this property
        accessible_projects = Project.objects.filter(
            Q(owner=request.user) | Q(viewers=request.user) | Q(contributors=request.user),
            property_lists__properties=property_obj
        ).distinct()

        if not accessible_projects.exists():
            return Response(
                {'error': 'You do not have access to this property'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Create or get favorite
        favorite, created = PropertyFavorite.objects.get_or_create(
            user=request.user,
            property=property_obj
        )

        return Response(
            {'status': 'added' if created else 'already_favorited'},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )

    def destroy(self, request, pk=None):
        """
        DELETE /api/property/favorites/{property_uuid}/

        Remove property from user's favorites.
        """
        try:
            favorite = PropertyFavorite.objects.get(
                user=request.user,
                property__uuid=pk
            )
            favorite.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except PropertyFavorite.DoesNotExist:
            return Response(
                {'error': 'Favorite not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class ProjectCommentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for ProjectComment CRUD.
    List/create filtered by project_uuid query param.
    Only the author can delete their own comment.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ProjectCommentSerializer
    lookup_field = 'uuid'

    def get_queryset(self):
        user = self.request.user
        queryset = ProjectComment.objects.filter(
            Q(project__owner=user) |
            Q(project__viewers=user) |
            Q(project__contributors=user)
        ).distinct()

        project_uuid = self.request.query_params.get('project')
        if project_uuid:
            queryset = queryset.filter(project__uuid=project_uuid)

        return queryset

    def perform_create(self, serializer):
        project_uuid = self.request.data.get('project_uuid')
        project = Project.objects.get(uuid=project_uuid)
        serializer.save(author=self.request.user, project=project)

    def destroy(self, request, *args, **kwargs):
        comment = self.get_object()
        if comment.author != request.user:
            return Response({'error': 'Only the author can delete this comment'}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)
