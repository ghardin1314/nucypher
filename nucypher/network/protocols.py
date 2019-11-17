"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import random
from collections import deque, namedtuple
from urllib.parse import urlparse

import maya
from eth_utils import is_checksum_address

from bytestring_splitter import VariableLengthBytestring
from twisted.internet.task import LoopingCall
from twisted.logger import Logger


class SuspiciousActivity(RuntimeError):
    """raised when an action appears to amount to malicious conduct."""


def parse_node_uri(uri: str):
    from nucypher.config.characters import UrsulaConfiguration

    if '@' in uri:
        checksum_address, uri = uri.split("@")
        if checksum_address is None:
            raise ValueError(f"{uri} is not a valid Teacher URI - no checksum address.")
        if not is_checksum_address(checksum_address):
            raise ValueError("{} is not a valid checksum address.".format(checksum_address))
    else:
        checksum_address = None  # federated

    #############################################
    # Strange logic here to ensure https:// - possibly pursuant to https://bugs.python.org/msg179670
    # It's not clear that there is any version of python 3.7+ that requires this, so we may
    # be able to drop it in the near future.
    if not uri.startswith("https://"):
        uri = "https://" + uri
    #############################################

    parsed_uri = urlparse(uri)

    if not parsed_uri.scheme:
        try:
            parsed_uri = urlparse('https://'+uri)
        except Exception:
            raise  # TODO: Do we need even deeper handling/validation here?

    if not parsed_uri.scheme == "https":
        raise ValueError("Invalid teacher scheme or protocol. Is the hostname prefixed with 'https://' ?")

    hostname = parsed_uri.hostname
    port = parsed_uri.port or UrsulaConfiguration.DEFAULT_REST_PORT
    return hostname, port, checksum_address


class InterfaceInfo:
    expected_bytes_length = lambda: VariableLengthBytestring

    def __init__(self, host, port) -> None:
        loopback, localhost = '127.0.0.1', 'localhost'
        self.host = loopback if host == localhost else host
        self.port = int(port)

    @classmethod
    def from_bytes(cls, url_string):
        host_bytes, port_bytes = url_string.split(b':', 1)
        port = int.from_bytes(port_bytes, "big")
        host = host_bytes.decode("utf-8")
        return cls(host=host, port=port)

    @property
    def uri(self):
        return u"{}:{}".format(self.host, self.port)

    @property
    def formal_uri(self):
        return u"{}://{}".format('https', self.uri)

    def __bytes__(self):
        return bytes(self.host, encoding="utf-8") + b":" + self.port.to_bytes(4, "big")

    def __add__(self, other):
        return bytes(self) + bytes(other)

    def __radd__(self, other):
        return bytes(other) + bytes(self)

    def __repr__(self):
        return self.uri


class AvailabilitySensor:

    DEFAULT_INTERVAL = 60 * 2    # Seconds
    DEFAULT_SAMPLE_SIZE = 3      # Ursulas
    DEFAULT_SENSITIVITY = 2      # Failure indication threshold
    DEFAULT_RETENTION = 10       # Records
    MAXIMUM_ALONE_TIME = 60 * 2  # Seconds

    class Unreachable(RuntimeError):
        pass

    Record = namedtuple('Record', ('time', 'result'))

    def __init__(self,
                 ursula,
                 interval: int = DEFAULT_INTERVAL,
                 sample_size: int = DEFAULT_SAMPLE_SIZE,
                 sensitivity: int = DEFAULT_SENSITIVITY,
                 retention: int = DEFAULT_RETENTION):

        self.log = Logger(self.__class__.__name__)
        self.interval = interval
        self.sample_size = sample_size
        self.sensitivity = sensitivity
        self.retention = retention
        self.warnings = {
            1: self.mild_warning,
            retention//2: self.medium_warning,
            retention: self.severe_warning
        }

        self._ursula = ursula
        self._sample_size = sample_size
        self._records = deque(maxlen=retention)

        self.__start_time = None
        self.__task = LoopingCall(self.maintain)

    def mild_warning(self) -> None:
        self.log.info(f'{self._ursula.rest_url} is unreachable')

    def medium_warning(self) -> None:
        self.log.warning(f'{self._ursula.rest_url} is unreachable')

    def severe_warning(self) -> None:
        self.log.critial(f'{self._ursula.rest_url} is unreachable')
        raise self.Unreachable(f'{self._ursula} is unreachable.')

    def handle_measurement_errors(self, *args, **kwargs) -> None:
        failure = args[0]
        cleaned_traceback = failure.getTraceback().replace('{', '').replace('}', '')  # FIXME: Amazing.
        self.log.warn("Unhandled error during availability check: {}".format(cleaned_traceback))

    @property
    def running(self) -> bool:
        return self.__task.running

    def start(self, now: bool = False):
        if not self.running:
            self.__start_time = maya.now().epoch
            d = self.__task.start(interval=self.interval, now=now)
            d.addErrback(self.handle_measurement_errors)

    def stop(self) -> None:
        if self.running:
            self.__task.stop()

    def maintain(self) -> None:
        if not self._ursula.known_nodes:
            # If there are no known nodes, skip this round...
            # ... but not for longer than the maximum allotted alone time
            if not self._ursula.lonely:
                now = maya.now().epoch
                delta = now - self.__start_time
                if delta >= self.MAXIMUM_ALONE_TIME:
                    self.severe_warning()
            return
        if len(self._ursula.known_nodes) < self.sample_size:
            # If there are fewer known nodes then the sample size, skip this round
            # TODO: How long can this be allowed for?
            return
        result = self.measure()
        self.record(result)
        self.issue_warnings()

    @property
    def score(self) -> float:
        failed_records = [record.result for record in self._records if record.result]
        return len(failed_records) / self.retention

    def issue_warnings(self) -> None:
        for threshold, action in self.warnings.items():
            if self.score >= threshold:
                action()

    def sample(self, quantity: int) -> list:
        ursulas = random.sample(population=self._ursula.known_nodes, k=quantity)
        return ursulas

    def record(self, result: bool) -> None:
        now = maya.now().epoch
        measurement = self.Record(time=now, result=result)
        self._records.append(measurement)

    def measure(self) -> bool:
        if self.sensitivity > self.sample_size:
            message = f"Threshold ({self.sensitivity}) cannot be greater then the sample size ({self.sample_size})."
            raise ValueError(message)
        ursulas = self.sample(quantity=self.sample_size)
        succeeded, failed = 0, 0
        for ursula in ursulas:
            response = self._ursula.network_middleware.measure(ursula)
            if response.status_code == 200:
                succeeded += 1
            else:
                failed += 1
        return failed >= self.sensitivity


