from cartography.graph.analysis import AddRelationship
from cartography.graph.analysis import AnalysisJob
from cartography.graph.analysis import AnalysisStatement
from cartography.graph.analysis import ScopeById

# Node labels an ACL can grant access to through GRANTS_ACCESS_TO.
_PROXMOX_ACL_RESOURCE_LABELS = (
    "ProxmoxVM",
    "ProxmoxStorage",
    "ProxmoxPool",
    "ProxmoxNode",
    "ProxmoxCluster",
)


def _user_permission_statement(resource_label: str) -> AnalysisStatement:
    # Zero hops: the ACL names the user (or one of its API tokens) directly.
    # One hop: the ACL names a group the user is a member of.
    return AnalysisStatement(
        comment=f"Users reach {resource_label} through their own ACLs or their groups' ACLs.",
        match=f"""
        MATCH (principal:ProxmoxUser)-[:MEMBER_OF_GROUP*0..1]->(grantee)
              <-[:APPLIES_TO_USER|APPLIES_TO_GROUP]-(acl:ProxmoxACL)
              -[:GRANTS_ACCESS_TO]->(resource:{resource_label})
        MATCH (acl)-[:GRANTS_ROLE]->(:ProxmoxRole)
        WITH DISTINCT principal, resource
        """,
        effects=(
            AddRelationship(
                "principal",
                "HAS_PERMISSION",
                "resource",
                source_label="ProxmoxUser",
                target_label=resource_label,
            ),
        ),
    )


def _group_permission_statement(resource_label: str) -> AnalysisStatement:
    return AnalysisStatement(
        comment=f"Groups reach {resource_label} through the ACLs that name them.",
        match=f"""
        MATCH (principal:ProxmoxGroup)<-[:APPLIES_TO_GROUP]-(acl:ProxmoxACL)
              -[:GRANTS_ACCESS_TO]->(resource:{resource_label})
        MATCH (acl)-[:GRANTS_ROLE]->(:ProxmoxRole)
        WITH DISTINCT principal, resource
        """,
        effects=(
            AddRelationship(
                "principal",
                "HAS_PERMISSION",
                "resource",
                source_label="ProxmoxGroup",
                target_label=resource_label,
            ),
        ),
    )


# One HAS_PERMISSION edge per principal and resource pair. The edge carries no
# ACL details because several ACLs can grant the same pair; follow the path
# through ProxmoxACL for the role, path, and propagation of each grant.
PROXMOX_EFFECTIVE_PERMISSIONS = AnalysisJob(
    name="Proxmox users and groups get effective permissions on resources",
    short_name="proxmox_effective_permissions",
    scope=ScopeById("ProxmoxCluster", "CLUSTER_ID", scope_on="principal"),
    statements=tuple(
        statement(label)
        for statement in (_user_permission_statement, _group_permission_statement)
        for label in _PROXMOX_ACL_RESOURCE_LABELS
    ),
)
