from __future__ import annotations

import json
import unittest
from pathlib import Path


TEMPLATE_PATH = (
    Path(__file__).parents[1]
    / "infra"
    / "athena-guardrails.template.json"
)


class CloudFormationTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
        cls.resources = cls.template["Resources"]

    def test_workgroup_enforces_server_side_controls(self) -> None:
        workgroup = self.resources["AthenaWorkGroup"]["Properties"]
        configuration = workgroup["WorkGroupConfiguration"]

        self.assertTrue(configuration["EnforceWorkGroupConfiguration"])
        self.assertTrue(configuration["PublishCloudWatchMetricsEnabled"])
        self.assertIn("BytesScannedCutoffPerQuery", configuration)
        self.assertEqual(
            configuration["ResultConfiguration"][
                "EncryptionConfiguration"
            ]["EncryptionOption"],
            "SSE_S3",
        )

    def test_results_bucket_is_private_encrypted_and_retained(self) -> None:
        bucket_resource = self.resources["AthenaResultsBucket"]
        properties = bucket_resource["Properties"]

        self.assertEqual(bucket_resource["DeletionPolicy"], "Retain")
        self.assertEqual(
            properties["BucketEncryption"][
                "ServerSideEncryptionConfiguration"
            ][0]["ServerSideEncryptionByDefault"]["SSEAlgorithm"],
            "AES256",
        )
        self.assertTrue(
            all(properties["PublicAccessBlockConfiguration"].values())
        )

    def test_alarm_uses_workgroup_processed_bytes(self) -> None:
        alarm = self.resources["ProcessedBytesAlarm"]["Properties"]

        self.assertEqual(alarm["Namespace"], "AWS/Athena")
        self.assertEqual(alarm["MetricName"], "ProcessedBytes")
        self.assertEqual(alarm["Statistic"], "Sum")
        self.assertEqual(alarm["Dimensions"][0]["Name"], "WorkGroup")
        self.assertEqual(
            alarm["Dimensions"][0]["Value"],
            {"Ref": "AthenaWorkGroup"},
        )

    def test_outputs_do_not_contain_account_specific_values(self) -> None:
        rendered = json.dumps(self.template)

        self.assertNotIn("arn:aws:", rendered)
        self.assertNotIn("123456789012", rendered)


if __name__ == "__main__":
    unittest.main()

