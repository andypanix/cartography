"""
Proxmox Virtual Environment intelligence module for Cartography.

This module syncs Proxmox infrastructure including clusters, nodes, VMs,
containers, storage, networks, users, and backup configurations.
"""

import logging
from collections.abc import Callable
from collections.abc import Iterable
from typing import Any
from typing import TYPE_CHECKING

import neo4j

if TYPE_CHECKING:
    from proxmoxer import ProxmoxAPI

from cartography.analysis.proxmox.analysis import PROXMOX_EFFECTIVE_PERMISSIONS
from cartography.config import Config
from cartography.graph.job import GraphJob
from cartography.intel.proxmox import access
from cartography.intel.proxmox import backup
from cartography.intel.proxmox import backup_coverage
from cartography.intel.proxmox import ceph
from cartography.intel.proxmox import certificate
from cartography.intel.proxmox import cluster
from cartography.intel.proxmox import compute
from cartography.intel.proxmox import firewall
from cartography.intel.proxmox import guests
from cartography.intel.proxmox import ha
from cartography.intel.proxmox import integrations
from cartography.intel.proxmox import mapping
from cartography.intel.proxmox import node_details
from cartography.intel.proxmox import pool
from cartography.intel.proxmox import replication
from cartography.intel.proxmox import sdn
from cartography.intel.proxmox import storage
from cartography.intel.proxmox import storage_content
from cartography.models.proxmox.access import ProxmoxACLSchema
from cartography.models.proxmox.access import ProxmoxAPITokenSchema
from cartography.models.proxmox.access import ProxmoxGroupSchema
from cartography.models.proxmox.access import ProxmoxRealmSchema
from cartography.models.proxmox.access import ProxmoxRealmSyncJobSchema
from cartography.models.proxmox.access import ProxmoxRoleSchema
from cartography.models.proxmox.access import ProxmoxTFAFactorSchema
from cartography.models.proxmox.access import ProxmoxUserSchema
from cartography.models.proxmox.backup import ProxmoxBackupJobSchema
from cartography.models.proxmox.certificate import ProxmoxCertificateSchema
from cartography.models.proxmox.compute import ProxmoxDiskSchema
from cartography.models.proxmox.compute import ProxmoxNetworkInterfaceSchema
from cartography.models.proxmox.compute import ProxmoxVMSchema
from cartography.models.proxmox.firewall import ProxmoxFirewallAliasSchema
from cartography.models.proxmox.firewall import ProxmoxFirewallIPSetSchema
from cartography.models.proxmox.firewall import ProxmoxFirewallRuleSchema
from cartography.models.proxmox.firewall import ProxmoxFirewallSecurityGroupSchema
from cartography.models.proxmox.guests import ProxmoxCustomCPUModelSchema
from cartography.models.proxmox.guests import ProxmoxGuestFilesystemSchema
from cartography.models.proxmox.guests import ProxmoxSnapshotSchema
from cartography.models.proxmox.ha import ProxmoxHAGroupSchema
from cartography.models.proxmox.ha import ProxmoxHALRMSchema
from cartography.models.proxmox.ha import ProxmoxHAManagerSchema
from cartography.models.proxmox.ha import ProxmoxHAResourceSchema
from cartography.models.proxmox.ha import ProxmoxHARuleSchema
from cartography.models.proxmox.integrations import ProxmoxACMEAccountSchema
from cartography.models.proxmox.integrations import ProxmoxMetricServerSchema
from cartography.models.proxmox.integrations import ProxmoxNotificationMatcherSchema
from cartography.models.proxmox.integrations import ProxmoxNotificationTargetSchema
from cartography.models.proxmox.mapping import ProxmoxResourceMappingSchema
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


class ProxmoxSyncError(Exception):
    """Raised at the end of a Proxmox sync in which one or more modules failed."""


class _ModuleRunner:
    """
    Run the steps of a Proxmox sync so that one failing module does not stop the others.

    A step that raises is logged with its traceback and its module is marked
    failed. The cleanup of a failed module is skipped, so its existing data
    stays in the graph until a later sync reads it again.
    """

    def __init__(self) -> None:
        self.failed: list[str] = []

    def ok(self, *modules: str) -> bool:
        """
        Tell whether none of the given modules failed.

        :param modules: Module names
        :return: True when no given module is marked failed
        """
        return not any(module in self.failed for module in modules)

    def run(
        self,
        module: str,
        step: Callable[..., Any],
        *args: Any,
        requires: Iterable[str] = (),
        action: str = "sync",
        **kwargs: Any,
    ) -> Any:
        """
        Run one step of a module and mark the module failed if the step raises.

        :param module: Module name, used in logs and in the final error
        :param step: Sync or cleanup function to call
        :param args: Positional arguments for the step
        :param requires: Modules whose output this step needs; when one of them
            failed, the step is not run and the module is marked failed
        :param action: What the step does, used in logs: "sync", "cleanup" or
            "analysis"
        :param kwargs: Keyword arguments for the step
        :return: The step result, or None when the step failed or was skipped
        """
        if module in self.failed:
            return None
        missing = [dependency for dependency in requires if dependency in self.failed]
        if missing:
            logger.error(
                "Skipping Proxmox %s %s because %s failed; keeping its existing data",
                module,
                action,
                ", ".join(missing),
            )
            self.failed.append(module)
            return None
        try:
            return step(*args, **kwargs)
        except Exception:
            logger.exception(
                "Proxmox %s %s failed; keeping its existing data and continuing "
                "with the other modules",
                module,
                action,
            )
            self.failed.append(module)
            return None


def _cleanup_schemas(*schemas: Any) -> Callable[[neo4j.Session, dict[str, Any]], None]:
    """
    Build a cleanup step that runs the node schema cleanup of each schema.

    :param schemas: Node schema instances
    :return: Cleanup function taking the Neo4j session and the job parameters
    """

    def _cleanup(
        neo4j_session: neo4j.Session, common_job_parameters: dict[str, Any]
    ) -> None:
        for schema in schemas:
            GraphJob.from_node_schema(schema, common_job_parameters).run(neo4j_session)

    return _cleanup


@timeit
def start_proxmox_ingestion(neo4j_session: neo4j.Session, config: Config) -> None:
    """
    Main entry point for Proxmox data ingestion.

    This is the primary sync function called by Cartography's sync orchestrator.

    The cluster and node sync runs first and stops the whole sync when it
    fails, because every other module needs the cluster ID. Each other module
    is isolated: when it raises, the error is logged with its traceback, its
    cleanup is skipped so its existing data stays, and the following modules
    still run. A module that needs the output of a failed module is skipped
    too. When any module failed, a ProxmoxSyncError naming the failed modules
    is raised at the end, so the Cartography run still reports the failure.

    :param neo4j_session: Neo4j session for database operations
    :param config: Cartography configuration object
    :raises ProxmoxSyncError: when one or more modules failed
    """
    if not config.proxmox_host:
        logger.info("Proxmox import is not configured - skipping this module.")
        return

    logger.info(f"Starting Proxmox infrastructure sync for {config.proxmox_host}")

    common_job_parameters: dict[str, Any] = {
        "UPDATE_TAG": config.update_tag,
    }

    # Get Proxmox API client
    proxmox_client = _get_proxmox_client(config)

    # Sync cluster and nodes, with their own cleanup. Not isolated: every other
    # module needs the cluster ID, so a failure here stops the sync.
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

    runner = _ModuleRunner()
    sync_args = (
        neo4j_session,
        proxmox_client,
        cluster_id,
        config.update_tag,
        common_job_parameters,
    )

    # Sync storage before compute so disks can link to their storage
    storage_status_map = runner.run("storage", storage.sync, *sync_args)

    # Sync the hyper-converged Ceph cluster, after storage so RBD and CephFS
    # storage can link to their pools and file systems. False means Ceph could
    # not be read, so its cleanup is skipped to keep the existing Ceph data.
    ceph_current = runner.run("ceph", ceph.sync, *sync_args)

    # Sync custom CPU models before compute so VMs can link to them
    runner.run(
        "custom CPU models",
        guests.sync_custom_cpu_models,
        neo4j_session,
        proxmox_client,
        cluster_id,
        config.update_tag,
    )

    # Sync VMs and containers, with their snapshots and guest details
    guest_mapping_refs = runner.run(
        "compute",
        compute.sync,
        *sync_args,
        enable_guest_agent=config.proxmox_enable_guest_agent,
    )

    runner.run("pool", pool.sync, *sync_args)
    runner.run("backup", backup.sync, *sync_args)

    # Sync backup coverage, storage content and replication after the guests,
    # disks, storage and backup jobs they link to. Storage content reads the
    # storages listed by the storage sync.
    runner.run("backup coverage", backup_coverage.sync, *sync_args)
    runner.run(
        "storage content",
        storage_content.sync,
        *sync_args,
        storage_status_map,
        requires=("storage",),
    )
    runner.run("replication", replication.sync, *sync_args)

    # Sync HA groups, resources, rules, and status
    runner.run("ha", ha.sync, *sync_args)

    # Sync access control (realms, users, tokens, TFA, groups, roles, ACLs)
    runner.run("access", access.sync, *sync_args)

    # Sync firewall options, rules, security groups, aliases, and IP sets
    firewall_references = runner.run("firewall", firewall.sync, *sync_args)

    # Sync SDN after compute and firewall: VNets link to guest interfaces, and
    # VNet firewall rules reuse the firewall rule model and link to the IP
    # sets, aliases, and security groups the firewall sync returned
    runner.run(
        "sdn",
        sdn.sync,
        *sync_args,
        firewall_references=firewall_references,
    )

    runner.run("certificate", certificate.sync, *sync_args)

    # Sync PCI, USB, and directory mappings and the VMs that use them. The VM
    # links come from the compute sync, so mappings wait for it.
    runner.run(
        "mapping",
        mapping.sync,
        *sync_args,
        guest_mapping_refs=guest_mapping_refs,
        requires=("compute",),
    )

    # Sync notification targets and matchers, metric servers, ACME accounts
    runner.run("integrations", integrations.sync, *sync_args)

    # Sync disks, storage, packages, repositories, subscription and system
    # settings of each online node; cleans up its own node types.
    runner.run("node details", node_details.sync, *sync_args)

    # Cleanup of each module that synced, after every module has loaded so
    # that relationships between modules are current. Each entry lists the
    # modules that must have succeeded for its cleanup to run. VNet firewall
    # rules are loaded by the SDN sync with the firewall rule model, so the
    # rule cleanup needs both.
    logger.info("Running Proxmox cleanup jobs")
    cleanups: list[tuple[tuple[str, ...], Callable[..., None]]] = [
        (
            ("compute",),
            _cleanup_schemas(
                ProxmoxVMSchema(),
                ProxmoxDiskSchema(),
                ProxmoxNetworkInterfaceSchema(),
                ProxmoxSnapshotSchema(),
                ProxmoxGuestFilesystemSchema(),
            ),
        ),
        (("custom CPU models",), _cleanup_schemas(ProxmoxCustomCPUModelSchema())),
        (("storage",), _cleanup_schemas(ProxmoxStorageSchema())),
        (("pool",), _cleanup_schemas(ProxmoxPoolSchema())),
        (("backup",), _cleanup_schemas(ProxmoxBackupJobSchema())),
        (
            ("ha",),
            _cleanup_schemas(
                ProxmoxHAGroupSchema(),
                ProxmoxHAResourceSchema(),
                ProxmoxHARuleSchema(),
                ProxmoxHAManagerSchema(),
                ProxmoxHALRMSchema(),
            ),
        ),
        (
            ("access",),
            _cleanup_schemas(
                ProxmoxUserSchema(),
                ProxmoxGroupSchema(),
                ProxmoxRoleSchema(),
                ProxmoxACLSchema(),
                ProxmoxAPITokenSchema(),
                ProxmoxTFAFactorSchema(),
                ProxmoxRealmSyncJobSchema(),
                ProxmoxRealmSchema(),
            ),
        ),
        (("firewall", "sdn"), _cleanup_schemas(ProxmoxFirewallRuleSchema())),
        (
            ("firewall",),
            _cleanup_schemas(
                ProxmoxFirewallIPSetSchema(),
                ProxmoxFirewallAliasSchema(),
                ProxmoxFirewallSecurityGroupSchema(),
            ),
        ),
        (("certificate",), _cleanup_schemas(ProxmoxCertificateSchema())),
        (("sdn",), sdn.cleanup),
        (("backup coverage",), backup_coverage.cleanup),
        (("storage content",), storage_content.cleanup),
        (("replication",), replication.cleanup),
        (("mapping",), _cleanup_schemas(ProxmoxResourceMappingSchema())),
        (
            ("integrations",),
            _cleanup_schemas(
                ProxmoxNotificationTargetSchema(),
                ProxmoxNotificationMatcherSchema(),
                ProxmoxMetricServerSchema(),
                ProxmoxACMEAccountSchema(),
            ),
        ),
    ]
    if ceph_current:
        cleanups.append((("ceph",), ceph.cleanup))
    elif runner.ok("ceph"):
        logger.warning("Skipping Ceph cleanup: the Ceph data could not be read")

    # A failing cleanup marks its module failed, so the later cleanups of that
    # module are skipped too; the skip log tells a failed cleanup apart from a
    # failed sync.
    failed_cleanups: set[str] = set()
    for modules, cleanup_step in cleanups:
        if runner.ok(*modules):
            runner.run(
                modules[0],
                cleanup_step,
                neo4j_session,
                common_job_parameters,
                action="cleanup",
            )
            if not runner.ok(modules[0]):
                failed_cleanups.add(modules[0])
        else:
            reasons = [
                f"the {module} {'cleanup' if module in failed_cleanups else 'sync'} "
                "failed"
                for module in modules
                if not runner.ok(module)
            ]
            logger.warning(
                "Skipping cleanup of Proxmox %s because %s",
                " and ".join(modules),
                " and ".join(reasons),
            )

    # Note: ProxmoxCluster doesn't need cleanup since it's the tenant root
    # and has no sub_resource_relationship

    # Derive HAS_PERMISSION from the ACL graph once every ACL, principal, and
    # resource edge is current, so stale grants are removed with the rest.
    # A partial access sync would remove grants that still exist, so the job
    # waits for the next sync in which access succeeds. The job runs as its own
    # step, so its failure is reported together with the other failed modules.
    if runner.ok("access"):
        runner.run(
            "effective permissions",
            run_typed_analysis_job,
            PROXMOX_EFFECTIVE_PERMISSIONS,
            neo4j_session,
            common_job_parameters,
            action="analysis",
        )
    else:
        logger.warning(
            "Skipping the Proxmox effective permissions analysis because the "
            "access sync failed",
        )

    if runner.failed:
        raise ProxmoxSyncError(
            "Proxmox sync failed for modules: " + ", ".join(runner.failed),
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
