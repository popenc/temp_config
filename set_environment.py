import os
import sys
import logging
from dotenv import load_dotenv
import platform
import requests
import json
import socket

logger = logging.getLogger(__name__)
logger.warning("set_environment.py")


class ServerConfig:
    """
    Handles server configurations that are laid out in
    the server_config.json file.
    """

    def __init__(self):

        self.server_configs_file = "temp_config/server_configs.json"  # filename for server configs
        self.server_key = "SERVER_NAME"  # server identifier key from server_configs.json
        self.env_file_key = "ENV"  # server_config.json key for env var filenames
        self.current_config = None  # env var file to load
        self.configs = []  # var for list of config objects from general json config
        self.read_json_config_file()  # loads server config json to configs attribute
        self.system_name = platform.system().upper()

    def read_json_config_file(self):
        """
        Reads in general json config as object, sets
        configs attribute.
        """
        with open(self.server_configs_file, 'r') as config_file:
            config_json = config_file.read()
            self.configs = json.loads(config_json)
        return True

    def get_config(self, server_name):
        """
        Searches through server_configs.json objects for a match
        for server_name. The SERVER_NAME in server_configs can be a
        substring/pattern as well (e.g., QedClusterBlue would match
        the QedCluster SERVER_NAME from server_configs.json).
        """
        for config_obj in self.configs:
            if config_obj[self.server_key] in server_name:
                self.current_config = config_obj[self.env_file_key]
                return self.current_config

    def set_current_config(self, server_name):
        """
        Sets config environment based on server_configs.json. Returns
        env var file to load based on server_name.
        """
        if server_name:
            self.current_config = self.get_config(server_name)
        else:
            self.current_config = None

        return self.current_config


class DeployEnv(ServerConfig):
    """
    Class for determining deploy env for running QED apps.
    """

    def __init__(self):

        ServerConfig.__init__(self)

        # Env vars used to determine server config:
        self.docker_hostname = None  # docker hostname (set in docker-compose using Bash $HOSTNAME)
        self.hostname = None  # HOSTNAME env var for Linux/Bash
        self.computer_name = None  # COMPUTERNAME env var for windows
        self.machine_id = None  # socket.gethostname() result - hostname where python is running
        self.aws_hostname = None  # sent in by saic/aws for green-prod or dev-blue

        # Test URL for determining if server is within EPA intranet:
        self.epa_access_test_url = 'https://qedinternal.epa.gov'
        if not self.epa_access_test_url:
            self.epa_access_test_url = 'https://qedinternal.epa.gov'

        self.env_path = "temp_config/environments/"  # path to .env files

    def determine_env(self):
        """
        Determines which .env file to use by matching machine name
        with server config in server_configs.json. First, tries
        machine id (socket.gethostname()), then hostname ($HOSTNAME),
        then computer name (%COMPUTERNAME%), and finally runs the original
        routine to automatically determine env if none of the above match.
        """

        # First, try matching docker hostname env var to SERVER_NAME:
        env_filename = self.set_current_config(self.docker_hostname)

        if not env_filename:
            # see if we are AWS
            env_filename = self.set_current_config(self.aws_hostname)
        else:
            logger.warning("Setting .env filename using $AWS_HOSTNAME.")
            return env_filename

        if not env_filename:
            # Try to find matching SERVER_NAME with machine id:
            env_filename = self.set_current_config(self.machine_id)
        else:
            logger.warning("Setting .env filename using $DOCKER_HOSTNAME.")
            return env_filename

        if not env_filename:
            # Next, try hostname ($HOSTNAME env var) if machine id doesn't match:
            env_filename = self.set_current_config(self.hostname)
        else:
            logger.warning("Setting .env filename using socket.gethostname().")
            return env_filename

        if not env_filename:
            # If machine id or hostname don't match, try %COMPUTERNAME% (Windows env var):
            env_filename = self.set_current_config(self.computer_name)
        else:
            logger.warning("Setting .env filename using $HOSTNAME env var.")
            return env_filename

        if not env_filename:
            # Finally, tries to automatically set environment if no machine id, hostname, or computer name:
            env_filename = self.run_auto_env_selector()
            return env_filename
        else:
            logger.warning("Setting .env filename using %COMPUTERNAME% env var.")
            return env_filename

        return None

    def load_deployment_environment(self):
        """
        This is called from the outside
        Looks through server_configs.json with ServerConfig class,
        then, if there's not a matching config, tries to automatically
        determine what .env file to use.
        """

        # env_filename = ''  # environment file name
        # server_name = self.get_machine_identifer()

        # Sets machine identifier attributes:
        self.aws_hostname = os.environ.get('AWS_HOSTNAME')
        self.docker_hostname = os.environ.get(
            'DOCKER_HOSTNAME')  # docker hostname (set in docker-compose using Bash $HOSTNAME)
        self.hostname = os.environ.get('HOSTNAME')  # HOSTNAME env var for Linux/Bash
        self.computer_name = os.environ.get('COMPUTERNAME')  # COMPUTERNAME env var for windows
        self.machine_id = socket.gethostname()  # returns string of hostname of machine where Python interpreter is currently executing (also see: socket.getfqdn())

        logger.warning("DOCKER_HOSTNAME: {}".format(self.docker_hostname))
        logger.warning("HOSTNAME: {}".format(self.hostname))
        logger.warning("COMPUTERNAME: {}".format(self.computer_name))
        logger.warning("MACHINE ID: {}".format(socket.gethostname()))
        logger.warning("AWS_HOSTNAME: {}".format(self.aws_hostname))

        env_filename = self.determine_env()  # gets .env filename by checking machine name with server_configs.json

        logger.warning("Loading env vars from: {}.".format(env_filename))

        dotenv_path = self.env_path + env_filename  # sets .env file path

        os.environ["SYSTEM_NAME"] = self.system_name #set system name (e.g. WINDOWS or LINUX or DARWIN)
        load_dotenv(dotenv_path)  # loads env vars into environment

        return env_filename

    def run_auto_env_selector(self):
        """
        Routine that tries determine what .env file to use automatically.
        Makes call to qedinternal to check if deployed in epa intranet, and
        checks for DOCKER_HOSTNAME env var to determine if docker or not.
        """
        # determine if inside or outside epa network
        internal_request = None
        try:
            # simple request to qed internal page to see if inside epa network:
            logger.warning("Testing for epa network access..")
            internal_request = requests.get(self.epa_access_test_url, verify=False, timeout=1)
        except Exception as e:
            logger.warning("Exception making request to qedinternal server.")
            logger.warning("User has no access to cgi servers at 134 addresses.")

        logger.warning("Response: {}".format(internal_request))

        if internal_request and internal_request.status_code == 200:
            logger.warning("Inside epa network.")
            if not self.docker_hostname:
                logger.warning("DOCKER_HOSTNAME not set, assumming local deployment.")
                logger.warning("Deploying with local epa environment.")
                return 'local_dev.env'
            else:
                return 'cgi_docker_dev.env'
                return 'this env no longer exists'
        else:
            logger.warning("Assuming outside epa network.")
            if not self.docker_hostname:
                logger.warning("DOCKER_HOSTNAME not set, assumming local deployment.")
                logger.warning("Deploying with local non-epa environment.")
                return 'local_dev.env'
            else:
                logger.warning("DOCKER_HOSTNAME: {}, Deploying with non-epa docker environment.")
                return 'local_docker_dev.env'

        return None
