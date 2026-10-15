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


@dataclass(frozen=True)
class ProxmoxCertificateNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Certificate ID in the form node_name:filename.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox cluster the certificate belongs to.",
    )
    node_name: PropertyRef = PropertyRef(
        "node_name",
        description="Name of the Proxmox node that uses the certificate.",
    )
    filename: PropertyRef = PropertyRef(
        "filename",
        extra_index=True,
        description="Certificate file name on the node.",
    )
    fingerprint: PropertyRef = PropertyRef(
        "fingerprint",
        extra_index=True,
        description="Certificate SHA-256 fingerprint.",
    )
    issuer: PropertyRef = PropertyRef(
        "issuer",
        description="Certificate issuer distinguished name.",
    )
    subject: PropertyRef = PropertyRef(
        "subject",
        description="Certificate subject distinguished name.",
    )
    san: PropertyRef = PropertyRef(
        "san",
        description="Subject alternative names of the certificate.",
    )
    notbefore: PropertyRef = PropertyRef(
        "notbefore",
        description="Start of the validity period as a Unix timestamp.",
    )
    notafter: PropertyRef = PropertyRef(
        "notafter",
        description="End of the validity period as a Unix timestamp.",
    )
    public_key_type: PropertyRef = PropertyRef(
        "public_key_type",
        description="Public key algorithm of the certificate.",
    )
    public_key_bits: PropertyRef = PropertyRef(
        "public_key_bits",
        description="Public key size in bits.",
    )
    pem: PropertyRef = PropertyRef(
        "pem",
        description="PEM-encoded certificate.",
    )


@dataclass(frozen=True)
class ProxmoxCertificateToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxCertificateToClusterRel(CartographyRelSchema):
    """The cluster contains the certificate."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxCertificateToClusterRelProperties = (
        ProxmoxCertificateToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxCertificateToNodeRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxCertificateToNodeRel(CartographyRelSchema):
    """The Proxmox node uses the certificate."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_name")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_CERTIFICATE"
    properties: ProxmoxCertificateToNodeRelProperties = (
        ProxmoxCertificateToNodeRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxCertificateSchema(CartographyNodeSchema):
    """A TLS certificate installed on a Proxmox VE node."""

    label: str = "ProxmoxCertificate"
    properties: ProxmoxCertificateNodeProperties = ProxmoxCertificateNodeProperties()
    sub_resource_relationship: ProxmoxCertificateToClusterRel = (
        ProxmoxCertificateToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxCertificateToNodeRel()],
    )
