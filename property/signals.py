from django.dispatch import receiver
from django_fsm.signals import post_transition
from property.models.stage1_models import StateTransitionLog


@receiver(post_transition)
def log_state_transition(sender, instance, name, source, target, **kwargs):
    """Auto-log all FSM state transitions"""
    StateTransitionLog.objects.create(
        content_object=instance,
        from_state=source,
        to_state=target,
        transition_name=name,
        triggered_by=getattr(instance, '_transition_user', None),
        triggered_by_system=(getattr(instance, '_transition_user', None) is None),
        metadata={
            'model': sender.__name__,
            'instance_id': instance.id
        }
    )
