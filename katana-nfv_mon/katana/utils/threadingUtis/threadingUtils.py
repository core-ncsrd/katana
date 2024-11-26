import threading
import logging

from katana.utils.mongoUtils import mongoUtils
from katana.utils.nfvoUtils import osmUtils

# Create the logger
logger = logging.getLogger(__name__)
stream_handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
stream_formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
stream_handler.setFormatter(stream_formatter)
logger.setLevel(logging.DEBUG)
logger.addHandler(stream_handler)


class MonThread(threading.Thread):
    """
    Class that implements a per Network Service thread for monitoring purposes
    """

    def __init__(self, ns, ns_status, ns_name, slice_id):
        super().__init__()
        self.ns = ns
        self.ns_status = ns_status
        self.ns_name = ns_name
        self.slice_id = slice_id
        # Create the stop parameter
        self._stop = threading.Event()

    def run(self):
        """
        The function that will run to check the NS status
        """
        while not self.stopped():
            target_nfvo = mongoUtils.find("nfvo", {"id": self.ns["nfvo-id"]})
            if target_nfvo["type"] == "OSM":
                target_nfvo_obj = osmUtils.Osm(
                    target_nfvo["id"],
                    target_nfvo["nfvoip"],
                    target_nfvo["nfvousername"],
                    target_nfvo["nfvopassword"],
                )
            else:
                logger.error("Not supported NFVO type")
                return
            insr = target_nfvo_obj.getNsr(self.ns["nfvo_inst_ns"])
            if not insr:
                self.ns_status.labels(self.slice_id, self.ns_name).set(2)
            elif insr["operational-status"] == "terminating":
                self.ns_status.labels(self.slice_id, self.ns_name).set(4)
            elif insr["operational-status"] != "running":
                self.ns_status.labels(self.slice_id, self.ns_name).set(3)
            self._stop.wait(timeout=10)

    def ns_stop(self):
        """
        Sets the status of the metric to 5 (admin stopped)
        """
        self.ns_status.labels(self.slice_id, self.ns_name).set(5)

    def stopped(self):
        """
        Checks if the thread has stopped
        """
        return self._stop.is_set()

    def stop(self):
        """
        Stops the thread
        """
        self._stop.set()
