import unittest
import subprocess
import json
import tempfile
import os
import sys

# Assuming the script is run from the root of the project (e.g., GenerativeAgentsCN)
# Adjust if necessary, or set PYTHONPATH environment variable
START_PY_PATH = os.path.join("generative_agents", "start.py")

# Personas list copied from generative_agents/start.py for test comparison
# This should be kept in sync if the main list changes.
DEFAULT_PERSONAS = [
    "阿伊莎", "克劳斯", "玛丽亚", "沃尔夫冈",
    "梅", "约翰", "埃迪",
    "简", "汤姆",
    "卡门", "塔玛拉",
    "亚瑟", "伊莎贝拉",
    "山姆", "詹妮弗",
    "弗朗西斯科", "海莉", "拉吉夫", "拉托亚",
    "阿比盖尔", "卡洛斯", "乔治", "瑞恩", "山本百合子", "亚当",
]

# Required data/config.json for get_config to run without error
# Ensure this file exists with minimal valid content if not already present
# For tests, we assume 'data/config.json' is accessible and valid as per start.py's usage.
# We also need a dummy 'results/checkpoints' directory for some tests.

class TestAgentFileScenarios(unittest.TestCase):

    def _run_start_py(self, args):
        """Helper function to run start.py with given arguments."""
        cmd = [sys.executable, START_PY_PATH] + args
        process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        return process.stdout, process.stderr, process.returncode

    def setUp(self):
        """Create dummy data/config.json and results/checkpoints if they don't exist."""
        self.data_config_dir = "generative_agents/data"
        self.data_config_path = os.path.join(self.data_config_dir, "config.json")
        self.checkpoints_dir = "generative_agents/results/checkpoints"
        self.test_sim_name = "test_sim_for_validation"
        self.test_sim_checkpoint_dir = os.path.join(self.checkpoints_dir, self.test_sim_name)


        # Ensure data/config.json exists
        os.makedirs(self.data_config_dir, exist_ok=True)
        if not os.path.exists(self.data_config_path):
            with open(self.data_config_path, "w", encoding="utf-8") as f:
                json.dump({
                    "agent": {"wake_up_hour": 8, "sleep_hour": 22}, # Minimal valid content
                    "api_keys": {} # Minimal valid content
                }, f)

        # Ensure results/checkpoints directory exists for resume tests (though not strictly needed for --validate-config)
        os.makedirs(self.checkpoints_dir, exist_ok=True)
        os.makedirs(self.test_sim_checkpoint_dir, exist_ok=True)


    # Test Cases will be added here

    def test_1_valid_agents_file(self):
        valid_agents = ["阿伊莎", "克劳斯"]
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8") as tmpfile:
            json.dump(valid_agents, tmpfile)
            tmpfile_path = tmpfile.name

        try:
            stdout, stderr, exit_code = self._run_start_py([
                "--validate-config",
                "--name", "test_valid",
                "--agents_file", tmpfile_path
            ])

            self.assertEqual(exit_code, 0, f"stderr: {stderr}")
            self.assertEqual(stderr, "")

            loaded_agents = json.loads(stdout)
            self.assertEqual(sorted(valid_agents), sorted(loaded_agents))
        finally:
            os.remove(tmpfile_path)

    def test_2_default_behavior_no_agents_file(self):
        stdout, stderr, exit_code = self._run_start_py([
            "--validate-config",
            "--name", "test_default"
        ])

        self.assertEqual(exit_code, 0, f"stderr: {stderr}")
        self.assertEqual(stderr, "")

        loaded_agents = json.loads(stdout)
        self.assertEqual(sorted(DEFAULT_PERSONAS), sorted(loaded_agents))

    def test_3_invalid_json_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8") as tmpfile:
            tmpfile.write("this is not valid json {")
            tmpfile_path = tmpfile.name

        try:
            stdout, stderr, exit_code = self._run_start_py([
                "--validate-config",
                "--name", "test_invalid_json",
                "--agents_file", tmpfile_path
            ])

            self.assertEqual(exit_code, 1)
            self.assertIn("invalid JSON", stderr)
            # Depending on when start.py exits, stdout might be empty or contain partial messages.
            # For now, primarily concerned with stderr and exit code.
            # self.assertEqual(stdout, "")
        finally:
            os.remove(tmpfile_path)

    def test_4_agents_file_not_found(self):
        non_existent_file = "non_existent_agents_file.json"
        # Ensure it really doesn't exist, in case a previous failed test left it.
        if os.path.exists(non_existent_file):
            os.remove(non_existent_file)

        stdout, stderr, exit_code = self._run_start_py([
            "--validate-config",
            "--name", "test_file_not_found",
            "--agents_file", non_existent_file
        ])

        self.assertEqual(exit_code, 1)
        self.assertIn("not found", stderr)
        # self.assertEqual(stdout, "")

    def test_5_agents_file_with_some_invalid_names(self):
        mixed_agents = ["阿伊莎", "InvalidAgent1", "克劳斯", "InvalidAgent2"]
        expected_valid_agents = ["阿伊莎", "克劳斯"]

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8") as tmpfile:
            json.dump(mixed_agents, tmpfile)
            tmpfile_path = tmpfile.name

        try:
            stdout, stderr, exit_code = self._run_start_py([
                "--validate-config",
                "--name", "test_some_invalid",
                "--agents_file", tmpfile_path
            ])

            self.assertEqual(exit_code, 0, f"stderr: {stderr}")
            # Check for warnings for each invalid agent
            self.assertIn("Warning: Agent name 'InvalidAgent1'", stderr)
            self.assertIn("not in the recognized personas list", stderr) # General check for the warning phrase
            self.assertIn("Warning: Agent name 'InvalidAgent2'", stderr)

            loaded_agents = json.loads(stdout)
            self.assertEqual(sorted(expected_valid_agents), sorted(loaded_agents))
        finally:
            os.remove(tmpfile_path)

    def test_6_agents_file_with_only_invalid_names(self):
        only_invalid_agents = ["InvalidAgent1", "CompletelyUnknown"]

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8") as tmpfile:
            json.dump(only_invalid_agents, tmpfile)
            tmpfile_path = tmpfile.name

        try:
            stdout, stderr, exit_code = self._run_start_py([
                "--validate-config",
                "--name", "test_only_invalid",
                "--agents_file", tmpfile_path
            ])

            self.assertEqual(exit_code, 1)
            # Check for warnings for each invalid agent first
            self.assertIn("Warning: Agent name 'InvalidAgent1'", stderr)
            self.assertIn("Warning: Agent name 'CompletelyUnknown'", stderr)
            # Check for the final error message
            self.assertIn("No valid agent names found", stderr)
            self.assertIn("match recognized personas", stderr)
            # self.assertEqual(stdout, "") # stdout might contain partial warnings before exit
        finally:
            os.remove(tmpfile_path)

    def test_7_agents_file_empty_list(self):
        empty_list = []

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8") as tmpfile:
            json.dump(empty_list, tmpfile)
            tmpfile_path = tmpfile.name

        try:
            stdout, stderr, exit_code = self._run_start_py([
                "--validate-config",
                "--name", "test_empty_list",
                "--agents_file", tmpfile_path
            ])

            self.assertEqual(exit_code, 1)
            # This scenario should also lead to "No valid agent names found"
            self.assertIn("No valid agent names found", stderr)
            self.assertIn("match recognized personas", stderr)
            # self.assertEqual(stdout, "")
        finally:
            os.remove(tmpfile_path)

    def test_8_agents_file_non_list_json(self):
        non_list_json = {"name": "阿伊莎", "description": "This is not a list"}

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8") as tmpfile:
            json.dump(non_list_json, tmpfile)
            tmpfile_path = tmpfile.name

        try:
            stdout, stderr, exit_code = self._run_start_py([
                "--validate-config",
                "--name", "test_non_list_json",
                "--agents_file", tmpfile_path
            ])

            self.assertEqual(exit_code, 1)
            self.assertIn("is not a list", stderr)
            # self.assertEqual(stdout, "")
        finally:
            os.remove(tmpfile_path)

    # Remove the dummy test as we have actual tests now
    # def test_dummy(self):
    #     self.assertTrue(True)

if __name__ == "__main__":
    unittest.main()
