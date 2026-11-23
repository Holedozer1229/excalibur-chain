import unittest

from integrations.camelot_fair.excal_client import ExcalClient, SWORDS_PER_EXCAL


class ExcalClientValidationTests(unittest.TestCase):
    def test_loopback_only(self):
        ExcalClient()
        with self.assertRaises(ValueError):
            ExcalClient("http://203.0.113.10:9432")
        with self.assertRaises(ValueError):
            ExcalClient("https://127.0.0.1:9432")

    def test_rpc_method_allowlist(self):
        client = ExcalClient()
        with self.assertRaises(ValueError):
            client._call("sendtoaddress", ["00" + "11" * 20, 1])
        with self.assertRaises(ValueError):
            client._call("sendrawtransaction", ["deadbeef"])

    def test_lock_validation(self):
        client = ExcalClient()
        with self.assertRaises(ValueError):
            client.get_utxos("ff")
        with self.assertRaises(ValueError):
            client.get_utxos("00" + "zz" * 20)

    def test_integer_denomination(self):
        self.assertEqual(SWORDS_PER_EXCAL, 100_000_000)


if __name__ == "__main__":
    unittest.main()
