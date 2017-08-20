class Client(object):
    """
    This is a dummy client which doesn't connect anywhere and just does
    re-encryptions. Needed only for tests and development. NOT for any real
    usage.

    Any client (dummy or not) should work similarly to ZEO client which runs in
    an asyncio event loop in a thread transparently. When user instantiates the
    class, a new thread with an event loop starts, and all the methods block.

    There is a _server attribute which is an async client=server (similar to
    that in kademlia).

    Initially, it is implemented here w/o networking or event loops, in a sync
    manner.
    """

    def __init__(self, **kw):
        self._storage = {}  # This will actually be remote!

    def store_rekeys(self, k, rekeys, algorithm):
        """
        :param bytes k: ID for the rekeys (or key in a key-value store sense)
        :param tuple rekeys: Rekeys to store. If bytes, it's just one rekey. If
            a tuple or a list of length > 1 - m-of-n reencryption is used.
        :param dict algorithm: Parameters of the re-encryption algo
        """
        pass

    def remove_rekeys(self, k):
        pass

    def reencrypt(self, k, ekey):
        """
        :param bytes k: Address of the rekey derived from the path/pubkey
        :param bytes ekey: Encrypted symmetric key to reencrypt
        """
        pass

    def close(self):
        """
        Disconnect from the network. In the dummy class - nothing here
        """
        pass