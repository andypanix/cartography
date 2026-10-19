"""
Proxmox Virtual Environment intelligence module for Cartography.

This module syncs Proxmox infrastructure including clusters, nodes, VMs,
containers, storage, networks, users, and backup configurations.
"""

import logging
from typing import TYPE_CHECKING

import neo4j

if TYPE_CHECKING:
    from proxmoxer import ProxmoxAPI

from cartography.analysis.proxmox.analysis import PROXMOX_EFFECTIVE_PERMISSIONS
from cartography.config import Config
from cartography.graph.job import GraphJob
from cartography.intel.proxmox import access
from cartography.intel.proxmox import backup
from cartography.intel.proxmox import certificate
from cartography.intel.proxmox import cluster
from cartography.intel.proxmox import compute
from cartography.intel.proxmox import firewall
from cartography.intel.proxmox import guests
from cartography.intel.proxmox import ha
from cartography.intel.proxmox import pool
from cartography.intel.proxmox import storage
from cartography.models.proxmox.access import ProxmoxACLSchema
from cartography.models.proxmox.access import ProxmoxGroupSchema
from cartography.models.proxmox.access import ProxmoxRoleSchema
from cartography.models.proxmox.access import ProxmoxUserSchema
from cartography.models.proxmox.backup import ProxmoxBackupJobSchema
from cartography.models.proxmox.certificate import ProxmoxCertificateSchema
from cartography.models.proxmox.cluster import ProxmoxNodeNetworkInterfaceSchema
from cartography.models.proxmox.cluster import ProxmoxNodeSchema
from cartography.models.proxmox.compute import ProxmoxDiskSchema
from cartography.models.proxmox.compute import ProxmoxNetworkInterfaceSchema
from cartography.models.proxmox.compute import ProxmoxVMSchema
from cartography.models.proxmox.firewall import ProxmoxFirewallIPSetSchema
from cartography.models.proxmox.firewall import ProxmoxFirewallRuleSchema
from cartography.models.proxmox.guests import ProxmoxCustomCPUModelSchema
from cartography.models.proxmox.guests import ProxmoxGuestFilesystemSchema
from cartography.models.proxmox.guests import ProxmoxSnapshotSchema
from cartography.models.proxmox.ha import ProxmoxHAGroupSchema
from cartography.models.proxmox.ha import ProxmoxHAResourceSchema
from cartography.models.proxmox.pool import ProxmoxPoolSchema
from cartography.models.proxmox.storage import ProxmoxStorageSchema
from cartography.stats import get_stats_client
from cartography.util import merge_module_sync_metadata
from cartography.util import run_typed_analysis_job
from cartography.util import timeit

logger = logging.getLogger(__name__)
stat_handler = get_stats_client(__name__)


def _get_proxmox_client(config: Config) -> "ProxmoxAPI":
    """
    Create a Proxmox API client, preferring API token over password authentication.

    :param config: Cartography configuration object
    :return: ProxmoxAPI client
    :raises ValueError: if no usable credentials are configured
    """
    from proxmoxer import ProxmoxAPI

    if config.proxmox_token_name and config.proxmox_token_value:
        logger.info("Connecting to Proxmox at %s using API token", config.proxmox_host)
        return ProxmoxAPI(
            config.proxmox_host,
            port=config.proxmox_port,
            user=config.proxmox_user,
            token_name=config.proxmox_token_name,
            token_value=config.proxmox_token_value,
            verify_ssl=config.proxmox_verify_ssl,
            timeout=config.proxmox_request_timeout,
        )

    if config.proxmox_password:
        logger.info(
            "Connecting to Proxmox at %s using password authentication",
            config.proxmox_host,
        )
        return ProxmoxAPI(
            config.proxmox_host,
            port=config.proxmox_port,
            user=config.proxmox_user,
            password=config.proxmox_password,
            verify_ssl=config.proxmox_verify_ssl,
            timeout=config.proxmox_request_timeout,
        )

    raise ValueError(
        "Proxmox credentials not configured: set --proxmox-token-name with "
        "--proxmox-token-value-env-var, or --proxmox-password-env-var.",
    )


@timeit
def start_proxmox_ingestion(neo4j_session: neo4j.Session, config: Config) -> None:
    """
    Main entry point for Proxmox data ingestion.

    This is the primary sync function called by Cartography's sync orchestrator.

    :param neo4j_session: Neo4j session for database operations
    :param config: Cartography configuration object
    """
    if not config.proxmox_host:
        logger.info("Proxmox import is not configured - skipping this module.")
        return

    logger.info(f"Starting Proxmox infrastructure sync for {config.proxmox_host}")

    common_job_parameters = {
        "UPDATE_TAG": config.update_tag,
    }

    # Get Proxmox API client
    proxmox_client = _get_proxmox_client(config)

    # Sync cluster and nodes (returns cluster_id for other modules)
    cluster_data = cluster.sync(
        neo4j_session,
        proxmox_client,
        config.proxmox_host,
        config.update_tag,
        common_job_parameters,
    )

    cluster_id = cluster_data["cluster_id"]

    # Add cluster_id to common_job_parameters for cleanup jobs
    common_job_parameters["CLUSTER_ID"] = cluster_id

    # Sync storage before compute so disks can link to their storage
    storage.sync(
        neo4j_session,
        proxmox_client,
        cluster_id,
        config.update_tag,
        common_job_parameters,
    )

    # Sync custom CPU models before compute so VMs can link to them
    guests.sync_custom_cpu_models(
        neo4j_session,
        proxmox_client,
        cluster_id,
        config.update_tag,
    )

    # Sync VMs and containers, with their snapshots and guest details
    compute.sync(
        neo4j_session,
        proxmox_client,
        cluster_id,
        config.update_tag,
        common_job_parameters,
        enable_guest_agent=config.proxmox_enable_guest_agent,
    )

    # Sync resource pools
    pool.sync(
        neo4j_session,
        proxmox_client,
        cluster_id,
        config.update_tag,
        common_job_parameters,
    )

    # Sync backup jobs
    backup.sync(
        neo4j_session,
        proxmox_client,
        cluster_id,
        config.update_tag,
        common_job_parameters,
    )

    # Sync HA groups and resources
    ha.sync(
        neo4j_session,
        proxmox_client,
        cluster_id,
        config.update_tag,
        common_job_parameters,
    )

    # Sync access control (users, groups, roles, ACLs)
    access.sync(
        neo4j_session,
        proxmox_client,
        cluster_id,
        config.update_tag,
        common_job_parameters,
    )

    # Sync firewall rules and IP sets
    firewall.sync(
        neo4j_session,
        proxmox_client,
        cluster_id,
        config.update_tag,
        common_job_parameters,
    )

    # Sync SSL/TLS certificates
    certificate.sync(
        neo4j_session,
        proxmox_client,
        cluster_id,
        config.update_tag,
        common_job_parameters,
    )

    # Run cleanup using modern GraphJob approach
    # Per AGENTS.md: Use GraphJob.from_node_schema() instead of JSON cleanup files
    logger.info("Running Proxmox cleanup jobs")

    # Cleanup all resource types scoped to this cluster
    GraphJob.from_node_schema(ProxmoxNodeSchema(), common_job_parameters).run(
        neo4j_session
    )
    GraphJob.from_node_schema(
        ProxmoxNodeNetworkInterfaceSchema(), common_job_parameters
    ).run(neo4j_session)
    GraphJob.from_node_schema(ProxmoxVMSchema(), common_job_parameters).run(
        neo4j_session
    )
    GraphJob.from_node_schema(ProxmoxDiskSchema(), common_job_parameters).run(
        neo4j_session
    )
    GraphJob.from_node_schema(
        ProxmoxNetworkInterfaceSchema(), common_job_parameters
    ).run(neo4j_session)
    for guest_schema in (
        ProxmoxSnapshotSchema(),
        ProxmoxGuestFilesystemSchema(),
        ProxmoxCustomCPUModelSchema(),
    ):
        GraphJob.from_node_schema(guest_schema, common_job_parameters).run(
            neo4j_session
        )
    GraphJob.from_node_schema(ProxmoxStorageSchema(), common_job_parameters).run(
        neo4j_session
    )
    GraphJob.from_node_schema(ProxmoxPoolSchema(), common_job_parameters).run(
        neo4j_session
    )
    GraphJob.from_node_schema(ProxmoxBackupJobSchema(), common_job_parameters).run(
        neo4j_session
    )
    GraphJob.from_node_schema(ProxmoxHAGroupSchema(), common_job_parameters).run(
        neo4j_session
    )
    GraphJob.from_node_schema(ProxmoxHAResourceSchema(), common_job_parameters).run(
        neo4j_session
    )
    GraphJob.from_node_schema(ProxmoxUserSchema(), common_job_parameters).run(
        neo4j_session
    )
    GraphJob.from_node_schema(ProxmoxGroupSchema(), common_job_parameters).run(
        neo4j_session
    )
    GraphJob.from_node_schema(ProxmoxRoleSchema(), common_job_parameters).run(
        neo4j_session
    )
    GraphJob.from_node_schema(ProxmoxACLSchema(), common_job_parameters).run(
        neo4j_session
    )
    GraphJob.from_node_schema(ProxmoxFirewallRuleSchema(), common_job_parameters).run(
        neo4j_session
    )
    GraphJob.from_node_schema(ProxmoxFirewallIPSetSchema(), common_job_parameters).run(
        neo4j_session
    )
    GraphJob.from_node_schema(ProxmoxCertificateSchema(), common_job_parameters).run(
        neo4j_session
    )

    # Note: ProxmoxCluster doesn't need cleanup since it's the tenant root
    # and has no sub_resource_relationship

    # Derive HAS_PERMISSION from the ACL graph once every ACL, principal, and
    # resource edge is current, so stale grants are removed with the rest.
    run_typed_analysis_job(
        PROXMOX_EFFECTIVE_PERMISSIONS,
        neo4j_session,
        common_job_parameters,
    )

    merge_module_sync_metadata(
        neo4j_session,
        group_type="ProxmoxCluster",
        group_id=cluster_id,
        synced_type="ProxmoxCluster",
        update_tag=config.update_tag,
        stat_handler=stat_handler,
    )

    logger.info("Completed Proxmox infrastructure sync")
