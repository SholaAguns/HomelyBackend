from .stage1_models import *
from .stage2_models import *
from .stage3_models import *


class StateTransitionLog(models.Model):
    """Audit trail for state transitions"""

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    from_state = models.CharField(max_length=30)
    to_state = models.CharField(max_length=30)
    transition_name = models.CharField(max_length=50)

    triggered_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    triggered_by_system = models.BooleanField(default=False)

    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'state_transition_logs'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.from_state} → {self.to_state} ({self.timestamp})"

