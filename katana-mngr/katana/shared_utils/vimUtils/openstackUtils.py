import functools
import logging
from logging import handlers
from multiprocessing import Process

import openstack

# Logging Parameters
logger = logging.getLogger(__name__)
file_handler = handlers.RotatingFileHandler("katana.log", maxBytes=10000, backupCount=5)
stream_handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
stream_formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
file_handler.setFormatter(formatter)
stream_handler.setFormatter(stream_formatter)
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)


def timeout(func):
    """
    Wrapper for function, terminate after 5 seconds
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        action = Process(target=func, args=args, kwargs=kwargs)
        action.start()
        action.join(timeout=5)
        if action.is_alive():
            # terminate function
            action.terminate()
            # clean up
            action.join()
            raise (TimeoutError)
        # if process is not 0, is not succesfull
        if action.exitcode != 0:
            # raise Attirbute Error, which is the most probable
            raise (AttributeError)

    return wrapper


class Openstack:
    """
    Class implementing the communication API with OpenStack
    """

    # Note: Cannot use conn as a self variable, as it is not possible to
    # serialize it and store it in a db

    def __init__(self, uuid, auth_url, project_name, username, password, verify=False, **kwargs):
        """
        Initialize an object of the class
        """
        self.uuid = uuid
        self.auth_url = auth_url
        self.project_name = project_name
        self.username = username
        self.password = password
        self.user_domain_name = "Default"
        self.project_domain_name = "default"
        self.verify = verify
        conn = openstack.connect(
            auth_url=auth_url,
            project_name=project_name,
            username=username,
            password=password,
            user_domain_name="Default",
            project_domain_name="default",
            verify=False  # Explicitly specify verify=False
        )
        try:
            conn.authorize()
        except AttributeError as e:
            logger.exception(e)
            logger.exception("AttributeError baby")
            self.auth_error = True
        except Exception as e:
            # raise for logging purposes
            logger.exception(e)
            logger.exception("Something went wrong")
            self.auth_error = True
        else:
            self.auth_error = False

    @timeout
    def openstack_authorize(self, conn):
        """
        Returns a token for the OpenStack instance
        """
        try:
            _ = conn.authorize()
        except AttributeError as e:
            logger.exception(e)
            logger.exception("AttributeError baby")
            return True
        except Exception as e:
            # raise for logging purposes
            logger.exception(e)
            logger.exception("Something went wrong")
            return True
        else:
            return False

    def create_project(self, conn, name, description="Katana Slice Project"):
        """
        Creates a new openstack project
        """
        project = conn.identity.create_project(name=name, description=description)
        # returns Project object
        return project

    def create_user(self, conn, name, password="password", description="Katana Slice User"):
        """
        Creates a new openstack project
        """
        user = conn.identity.create_user(name=name, password=password, description=description)
        return user

    def combine_proj_user(self, conn, project, user, vim_admin_user):
        """
        Compbines newly created project and user
        """
        userrole = conn.identity.find_role("user")
        heatrole = conn.identity.find_role("heat_stack_owner")
        conn.identity.assign_project_role_to_user(project, user, userrole)
        conn.identity.assign_project_role_to_user(project, user, heatrole)
        # Add admin user to the project, in order to create the MAC Addresses
        adminrole = conn.identity.find_role("admin")
        admin_user = conn.identity.find_user(vim_admin_user, ignore_missing=False)
        conn.identity.assign_project_role_to_user(project, admin_user, adminrole)
        conn.identity.assign_project_role_to_user(project, admin_user, heatrole)

    def create_sec_group(self, conn, name, project):
        """
        Creates the security group to be assigned to the new tenant
        """
        sec_group = conn.create_security_group(
            name=name, description="Katana Security Group", project_id=project.id
        )
        conn.create_security_group_rule(sec_group)
        return sec_group

    def delete_user(self, conn, name):
        """
        Deletes the user
        """
        user = conn.identity.find_user(name, ignore_missing=False)
        conn.identity.delete_user(user, ignore_missing=False)

    def delete_project(self, conn, name):
        """
        Deletes the project
        """
        project = conn.identity.find_project(name, ignore_missing=False)
        conn.identity.delete_project(project, ignore_missing=False)

    def delete_sec_group(self, conn, name):
        """
        Deletes the security group
        """
        conn.delete_security_group(name)

    def delete_proj_user(self, tenant):
        conn = openstack.connect(
            auth_url=self.auth_url,
            project_name=self.project_name,
            username=self.username,
            password=self.password,
            verify=self.verify  # Ensure SSL verification is disabled here
        )
        self.openstack_authorize(conn)
        user_name = tenant
        proj_name = tenant

        # Find Project and User
        project = conn.identity.find_project(proj_name, ignore_missing=False)
        user = conn.identity.find_user(user_name, ignore_missing=False)
        sec_group_list = []
        for sec_group in conn.network.security_groups():
            if sec_group.project_id == project.id:
                sec_group_list.append(sec_group)
        try:
            conn.identity.delete_user(user, ignore_missing=False)
        except openstack.exceptions.ResourceNotFound as e:
            logger.exception(e)
            logger.exception("Failed. User trying to delete, doesn't exist")
        try:
            conn.identity.delete_project(project, ignore_missing=False)
        except openstack.exceptions.ResourceNotFound as e:
            logger.exception(e)
            logger.exception("Failed. Project trying to delete, doesn't exist")
        for sec_group in sec_group_list:
            try:
                conn.delete_security_group(sec_group.id)
            except openstack.exceptions.ResourceNotFound as e:
                logger.exception("Failed. Security group trying to delete, doesn'texist", e)

    def set_quotas(self, name, quotas):
        """
        Sets the quotas of the tenant with default values dynamically retrieved from OpenStack if not provided
        """
        conn = openstack.connect(
            auth_url=self.auth_url,
            project_name=self.project_name,
            username=self.username,
            password=self.password,
            user_domain_name=self.user_domain_name,
            project_domain_name=self.project_domain_name,
            verify=self.verify,
        )
        self.openstack_authorize(conn)
        
        # Retrieve the current quotas to use as defaults
        current_quotas = conn.get_compute_quotas(name_or_id=name)

        # Setting dynamic default quota values if not explicitly provided
        kwargs = {
            "ram": round((quotas.get("memory-mb", current_quotas.get("ram", 16000)) + 200) / 100) * 100,
            "cores": quotas.get("vcpu-count", current_quotas.get("cores", 10)),
            "instances": quotas.get("instances", current_quotas.get("instances", 5))
        }

        try:
            conn.set_compute_quotas(name_or_id=name, **kwargs)
        except (openstack.exceptions.BadRequestException, TypeError) as e:
            logger.exception("Bad set quota request was made. Quotas didn't change", e)

    def create_slice_prerequisites(
        self,
        tenant_project_name,
        tenant_project_description,
        tenant_project_user,
        tenant_project_password,
        slice_uuid,
        quotas=None,
    ):
        """
        Creates the tenant (project, user, security_group) on the specivied vim
        """
        conn = openstack.connect(
            auth_url=self.auth_url,
            project_name=self.project_name,
            username=self.username,
            password=self.password,
            user_domain_name=self.user_domain_name,
            project_domain_name=self.project_domain_name,
            verify=self.verify,
        )
        self.openstack_authorize(conn)
        # creates the project in Openstack
        project = self.create_project(conn, tenant_project_name, tenant_project_description)

        # creates the user
        user = self.create_user(conn, tenant_project_user, "password")

        # assigns some needed roles
        self.combine_proj_user(conn, project, user, self.username)

        # creates the security group and rules
        sec_group = self.create_sec_group(conn, tenant_project_name, project)

        if quotas:
            self.set_quotas(project.name, quotas)
        return {
            "sliceProjectName": project.name,
            "sliceUserName": user.name,
            "secGroupName": sec_group.name,
        }

    # list_hypervisors() and other useful functions available
    # for the "Connection Object" can be found here:
    #  - https://docs.openstack.org/openstacksdk/latest/user/connection.html
        #
    def get_resources(self):
        conn = openstack.connect(
            auth_url=self.auth_url,
            project_name=self.project_name,
            username=self.username,
            password=self.password,
            user_domain_name=self.user_domain_name,
            project_domain_name=self.project_domain_name,
        )
        self.openstack_authorize(conn)

        # Initialize the report dictionary
        report = {
            "memory_mb": 0,
            "free_ram_mb": 0,
            "vcpus": 0,
            "vcpus_used": 0,
            "local_gb": 0,
            "local_gb_used": 0,
            "running_vms": 0,
            "vcpuse_available": 0,
            "compute_nodes": 0,
        }

        try:
            # Fetch hypervisor statistics using Nova API
            stats = conn.compute.get('/os-hypervisors/statistics', microversion='2.28').json()
            nova_stats = stats.get("hypervisor_statistics", {})

            # Populate the report dictionary
            report["memory_mb"] = nova_stats.get("memory_mb", 0)
            report["free_ram_mb"] = nova_stats.get("memory_mb", 0) - nova_stats.get("memory_mb_used", 0)
            report["vcpus"] = nova_stats.get("vcpus", 0)
            report["vcpus_used"] = nova_stats.get("vcpus_used", 0)
            report["local_gb"] = nova_stats.get("local_gb", 0)
            report["local_gb_used"] = nova_stats.get("local_gb_used", 0)
            report["running_vms"] = nova_stats.get("running_vms", 0)
            report["vcpuse_available"] = report["vcpus"] - report["vcpus_used"]
            report["compute_nodes"] = nova_stats.get("count", 0)

        except Exception as e:
            print(f"Failed to retrieve Nova statistics: {e}")

        return report
