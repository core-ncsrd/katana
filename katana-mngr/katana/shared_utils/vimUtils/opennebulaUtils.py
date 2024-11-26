import functools
import logging
from logging import handlers
from multiprocessing import Process

import pyone

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


class Opennebula:
    """
    Class implementing the communication API with OpenNebula
    """

    # Note: Cannot use conn as a self variable, as it is not possible to
    # serialize it and store it in a db

    def __init__(self, uuid, auth_url, project_name, username, password):
        """
        Initialize an object of the class
        """
        self.uuid = uuid
        self.auth_url = auth_url
        self.project_name = project_name
        self.username = username
        self.password = password
        conn = pyone.OneServer(self.auth_url, session=f"{username}:{password}")

    def create_project(self, conn, name, description="Katana Slice Project"):
        """
        Creates a new OpenNebula group
        """
        group = conn.group.allocate(name, description)
        # returns Project object
        return group

    def create_user(self, conn, name, password, group):
        """
        Creates a new openstack project
        """
        user = conn.user.allocate(name, password, "", [group])
        return user

    def create_sec_group(self, conn, name, project):
        """
        Creates the security group to be assigned to the new tenant
        """
        sec_group = conn.create_security_group(name=name, description="Katana Security Group", project_id=project.id)
        conn.create_security_group_rule(sec_group)
        return sec_group

    def delete_user(self, conn, user_id):
        """
        Deletes the user
        """
        try:
            return conn.user.delete(user_id)
        except pyone.OneNoExistsException as e:
            logger.exception("Failed. Trying to delete user: doesn't exist - ", user_id)
        except Exception as e:
            logger.exception("Failed. Trying to delete user: ", user_id)

    def delete_user_by_name(self, conn, name):
        """
        Deletes the user
        """
        userpool = conn.userpool.info(-1, -1, -1)
        for user in userpool.USER:
            if user.get_NAME() == name:
                return conn.user.delete(user.get_ID())

    def delete_project(self, conn, group_id):
        """
        Deletes the group
        """
        try:
            return conn.group.delete(group_id)
        except pyone.OneNoExistsException as e:
            logger.exception("Failed. Trying to delete group: doesn't exist - ", group_id)
        except Exception as e:
            logger.exception("Failed. Trying to delete group: ", group_id)

    def delete_project_by_name(self, conn, name):
        """
        Deletes the group
        """
        grouppool = conn.grouppool.info(-1, -1, -1)
        for group in grouppool.GROUP:
            if group.get_NAME() == name:
                return conn.group.delete(group.get_ID())

    def delete_proj_user(self, user_id):
        """
        Deletes user and project
        """
        conn = pyone.OneServer(self.auth_url, session=f"{self.username}:{self.password}")
        try:
            user = conn.user.info(user_id)
            group = user.get_GROUPS().ID[0]
            # delete group
            conn.group.delete(group)
            # delete user
            return conn.user.delete(user.get_ID())
        except pyone.OneNoExistsException as e:
            logger.exception("Failed. User trying to delete, doesn't exist: ", user_id)
        except Exception as e:
            logger.exception("Failed. User trying to delete, group doesn't exist: ", user_id)

    def delete_proj_user_by_name(self, name):
        """
        Deletes user and project
        """
        conn = pyone.OneServer(self.auth_url, session=f"{self.username}:{self.password}")
        userpool = conn.userpool.info(-1, -1, -1)
        for user in userpool.USER:
            if user.get_NAME() == name:
                group = user.get_GROUPS()[0]
                # delete group
                conn.group.delete(group)
                # delete user
                return conn.user.delete(user.get_ID())
        logger.warning("Delete user ONE: user does not exist: ", name)

    def create_slice_prerequisites(
        self, tenant_project_name, tenant_project_description, tenant_project_user, tenant_project_password, slice_uuid,
    ):
        """
        Creates the tenant (project, user, security_group) on the specified vim
        """
        conn = pyone.OneServer(self.auth_url, session=f"{self.username}:{self.password}")
        # creates the project in OpenNebula
        project = self.create_project(conn, tenant_project_name, tenant_project_description)

        # creates the user
        user = self.create_user(conn, tenant_project_user, "password", project)

        # creates the security group and rules
        # sec_group = self.create_sec_group(conn, tenant_project_name, project)
        sec_group = "dummy"

        return {"sliceProjectName": project, "sliceUserName": user, "secGroupName": sec_group}
