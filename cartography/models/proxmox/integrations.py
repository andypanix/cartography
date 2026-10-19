from dataclasses import dataclass

from cartography.models.core.common import PropertyRef
from cartography.models.core.nodes import CartographyNodeProperties
from cartography.models.core.nodes import CartographyNodeSchema
from cartography.models.core.relationships import CartographyRelProperties
from cartography.models.core.relationships import CartographyRelSchema
from cartography.models.core.relationships import LinkDirection
from cartography.models.core.relationships import make_target_node_matcher
from cartography.models.core.relationships import OtherRelationships
from cartography.models.core.relationships import TargetNodeMatcher

# ============================================================================
# Notification targets
# ============================================================================


@dataclass(frozen=True)
class ProxmoxNotificationTargetNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Notification target ID in the form cluster_id/name.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Name of the notification target (endpoint), unique across endpoint types.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that defines the notification target.",
    )
    type: PropertyRef = PropertyRef(
        "type",
        description="Endpoint type: sendmail, smtp, gotify, or webhook.",
    )
    comment: PropertyRef = PropertyRef("comment", description="Target comment.")
    disable: PropertyRef = PropertyRef(
        "disable",
        description="Whether the target is disabled.",
    )
    origin: PropertyRef = PropertyRef(
        "origin",
        description="Whether the target is user-created, builtin, or modified-builtin.",
    )
    author: PropertyRef = PropertyRef(
        "author",
        description="Author shown in the mail, for sendmail and smtp endpoints.",
    )
    from_address: PropertyRef = PropertyRef(
        "from_address",
        description="From address of the mail, for sendmail and smtp endpoints.",
    )
    mailto: PropertyRef = PropertyRef(
        "mailto",
        description="Email recipients, for sendmail and smtp endpoints.",
    )
    mailto_user: PropertyRef = PropertyRef(
        "mailto_user",
        description="Proxmox users whose email address receives the mail, for sendmail and smtp endpoints.",
    )
    mode: PropertyRef = PropertyRef(
        "mode",
        description="Encryption of the SMTP connection: insecure, starttls, or tls.",
    )
    server: PropertyRef = PropertyRef(
        "server",
        description="SMTP server address, or the scheme, host and port of the gotify or webhook URL. The URL path and query are not stored because they can carry tokens.",
    )
    port: PropertyRef = PropertyRef(
        "port",
        description="Port of the SMTP server.",
    )
    username: PropertyRef = PropertyRef(
        "username",
        description="Username for SMTP authentication. The password is not stored.",
    )
    method: PropertyRef = PropertyRef(
        "method",
        description="HTTP method of the webhook: post, put, or get.",
    )
    header_names: PropertyRef = PropertyRef(
        "header_names",
        description="Names of the HTTP headers the webhook sets. Header values are not stored.",
    )
    secret_names: PropertyRef = PropertyRef(
        "secret_names",
        description="Names of the secrets the webhook defines. Secret values are not stored.",
    )


@dataclass(frozen=True)
class ProxmoxNotificationTargetToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxNotificationTargetToClusterRel(CartographyRelSchema):
    """The cluster contains the notification target."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxNotificationTargetToClusterRelProperties = (
        ProxmoxNotificationTargetToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxNotificationTargetToUserRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxNotificationTargetToUserRel(CartographyRelSchema):
    """The mail notification target sends notifications to the email address of the Proxmox user."""

    target_node_label: str = "ProxmoxUser"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("mailto_user_ids", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "NOTIFIES"
    properties: ProxmoxNotificationTargetToUserRelProperties = (
        ProxmoxNotificationTargetToUserRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxNotificationTargetSchema(CartographyNodeSchema):
    """A notification endpoint (sendmail, SMTP, gotify, or webhook) that a Proxmox VE cluster sends notifications to."""

    label: str = "ProxmoxNotificationTarget"
    properties: ProxmoxNotificationTargetNodeProperties = (
        ProxmoxNotificationTargetNodeProperties()
    )
    sub_resource_relationship: ProxmoxNotificationTargetToClusterRel = (
        ProxmoxNotificationTargetToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxNotificationTargetToUserRel()],
    )


# ============================================================================
# Notification matchers
# ============================================================================


@dataclass(frozen=True)
class ProxmoxNotificationMatcherNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Notification matcher ID in the form cluster_id/name.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Name of the notification matcher.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that defines the matcher.",
    )
    comment: PropertyRef = PropertyRef("comment", description="Matcher comment.")
    disable: PropertyRef = PropertyRef(
        "disable",
        description="Whether the matcher is disabled.",
    )
    origin: PropertyRef = PropertyRef(
        "origin",
        description="Whether the matcher is user-created, builtin, or modified-builtin.",
    )
    mode: PropertyRef = PropertyRef(
        "mode",
        description="Whether all or any of the match rules must match.",
    )
    invert_match: PropertyRef = PropertyRef(
        "invert_match",
        description="Whether the result of the whole matcher is inverted.",
    )
    match_calendar: PropertyRef = PropertyRef(
        "match_calendar",
        description="Calendar events the notification timestamp must match.",
    )
    match_field: PropertyRef = PropertyRef(
        "match_field",
        description="Metadata field rules in the form (regex|exact):<field>=<value>.",
    )
    match_severity: PropertyRef = PropertyRef(
        "match_severity",
        description="Notification severities the matcher matches.",
    )
    targets: PropertyRef = PropertyRef(
        "targets",
        description="Names of the notification targets notified on match.",
    )


@dataclass(frozen=True)
class ProxmoxNotificationMatcherToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxNotificationMatcherToClusterRel(CartographyRelSchema):
    """The cluster contains the notification matcher."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxNotificationMatcherToClusterRelProperties = (
        ProxmoxNotificationMatcherToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxNotificationMatcherToTargetRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxNotificationMatcherToTargetRel(CartographyRelSchema):
    """The matcher sends the notifications it matches to the notification target."""

    target_node_label: str = "ProxmoxNotificationTarget"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("target_ids", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "ROUTES_TO"
    properties: ProxmoxNotificationMatcherToTargetRelProperties = (
        ProxmoxNotificationMatcherToTargetRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxNotificationMatcherSchema(CartographyNodeSchema):
    """A notification matcher that routes Proxmox VE notifications to targets by severity, field, and time."""

    label: str = "ProxmoxNotificationMatcher"
    properties: ProxmoxNotificationMatcherNodeProperties = (
        ProxmoxNotificationMatcherNodeProperties()
    )
    sub_resource_relationship: ProxmoxNotificationMatcherToClusterRel = (
        ProxmoxNotificationMatcherToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxNotificationMatcherToTargetRel()],
    )


# ============================================================================
# Metric servers
# ============================================================================


@dataclass(frozen=True)
class ProxmoxMetricServerNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Metric server ID in the form cluster_id/server_id.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    server_id: PropertyRef = PropertyRef(
        "server_id",
        extra_index=True,
        description="ID of the metric server entry inside the cluster.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that sends metrics to the server.",
    )
    type: PropertyRef = PropertyRef(
        "type",
        description="Metric server plugin type, such as influxdb or graphite.",
    )
    server: PropertyRef = PropertyRef(
        "server",
        description="DNS name or IP address of the metric server.",
    )
    port: PropertyRef = PropertyRef(
        "port",
        description="Network port of the metric server.",
    )
    disable: PropertyRef = PropertyRef(
        "disable",
        description="Whether sending metrics to the server is disabled.",
    )


@dataclass(frozen=True)
class ProxmoxMetricServerToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxMetricServerToClusterRel(CartographyRelSchema):
    """The cluster contains the metric server configuration."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxMetricServerToClusterRelProperties = (
        ProxmoxMetricServerToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxMetricServerSchema(CartographyNodeSchema):
    """An external metric server (InfluxDB or Graphite) that a Proxmox VE cluster sends performance data to."""

    label: str = "ProxmoxMetricServer"
    properties: ProxmoxMetricServerNodeProperties = ProxmoxMetricServerNodeProperties()
    sub_resource_relationship: ProxmoxMetricServerToClusterRel = (
        ProxmoxMetricServerToClusterRel()
    )


# ============================================================================
# ACME accounts
# ============================================================================


@dataclass(frozen=True)
class ProxmoxACMEAccountNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="ACME account ID in the form cluster_id/name.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Name of the ACME account configuration.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that registered the account.",
    )
    directory: PropertyRef = PropertyRef(
        "directory",
        description="URL of the ACME CA directory endpoint. Set only when the account details are readable.",
    )
    location: PropertyRef = PropertyRef(
        "location",
        description="URL of the account at the ACME CA. Set only when the account details are readable.",
    )
    tos: PropertyRef = PropertyRef(
        "tos",
        description="URL of the terms of service accepted for the account. Set only when the account details are readable.",
    )
    contact: PropertyRef = PropertyRef(
        "contact",
        description="Contact URLs of the account, such as mailto:admin@example.com. Set only when the account details are readable.",
    )
    status: PropertyRef = PropertyRef(
        "status",
        description="Account status reported by the ACME CA, such as valid or deactivated. Set only when the account details are readable.",
    )


@dataclass(frozen=True)
class ProxmoxACMEAccountToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxACMEAccountToClusterRel(CartographyRelSchema):
    """The cluster contains the ACME account."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxACMEAccountToClusterRelProperties = (
        ProxmoxACMEAccountToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxACMEAccountSchema(CartographyNodeSchema):
    """An account at an ACME certificate authority that a Proxmox VE cluster uses to order node certificates."""

    label: str = "ProxmoxACMEAccount"
    properties: ProxmoxACMEAccountNodeProperties = ProxmoxACMEAccountNodeProperties()
    sub_resource_relationship: ProxmoxACMEAccountToClusterRel = (
        ProxmoxACMEAccountToClusterRel()
    )
