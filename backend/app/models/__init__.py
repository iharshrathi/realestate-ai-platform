"""Importing this package registers every table on ``Base.metadata``."""

from app.models.agent_log import AgentLog
from app.models.campaign import MarketingCampaign
from app.models.follow_up import FollowUp
from app.models.interaction import LeadInteraction
from app.models.lead import Lead
from app.models.prediction import Prediction
from app.models.property import Property
from app.models.requirement import CustomerRequirement
from app.models.user import User

__all__ = [
    "AgentLog",
    "CustomerRequirement",
    "FollowUp",
    "Lead",
    "LeadInteraction",
    "MarketingCampaign",
    "Prediction",
    "Property",
    "User",
]
