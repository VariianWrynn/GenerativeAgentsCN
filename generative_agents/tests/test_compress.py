import unittest
from datetime import datetime

from generative_agents.compress import (
    _process_checkpoints_to_movement_data,
    insert_frame0,  # Not directly tested here but used by _process_checkpoints_to_movement_data
    get_stride_from_checkpoints, # Not directly tested here but used by _process_checkpoints_to_movement_data
    get_location # Helper that might be useful for assertions
)
from generative_agents.modules.maze import Maze
from generative_agents.tests.test_replay_failsafe_data import (
    mock_schedule_failsafe_data,
    mock_action_failsafe_data
)

# From compress.py
FRAMES_PER_STEP = 60

class MockMaze(Maze):
    def __init__(self, maze_data=None, logger=None):
        # Minimal init for Maze that compress.py might rely on.
        # Based on compress.py, Maze is instantiated with maze_data and None (presumably for logger).
        # The actual maze_data structure is not critical if find_path is mocked.
        self.tile_size = 16 # Example, if needed by any Maze methods called indirectly.
        self.maze_data = maze_data if maze_data is not None else {"width": 0, "height": 0, "tiles": {}}


    def find_path(self, source_coord, target_coord):
        if list(source_coord) == list(target_coord):
            return [list(source_coord)]
        # Return a direct path for simplicity in tests
        return [list(source_coord), list(target_coord)]

def mock_static_agent_data_loader(agent_name, base_path="frontend/static/assets/village/agents"):
    """
    Returns a dictionary representing the content of a static agent.json file.
    """
    # This needs to match the structure expected by insert_frame0 and potentially other parts
    # of _process_checkpoints_to_movement_data if it accesses more from static data.
    # insert_frame0 uses: json_data["spatial"]["address"]["living_area"], json_data["coord"],
    #                     json_data["currently"], json_data["scratch"]
    return {
        "name": agent_name, # For completeness
        "spatial": {
            "address": {
                "living_area": ["<world>", "house", f"{agent_name}'s bedroom"]
            }
        },
        "coord": [10, 10],  # Default initial coordinates
        "currently": f"{agent_name} is initially idle.",
        "scratch": { # Used by insert_frame0 (via all_movement["description"])
            "age": 30,
            "innate": "calm",
            "learned": "reading",
            "lifestyle": "early bird",
            # Other fields from agent.json's scratch if needed by compress.py logic
        }
    }

class TestCompressWithFailsafeSchedule(unittest.TestCase):
    def test_process_schedule_failsafe_data(self):
        agent_name = "TestAgentSchedule"
        current_time = datetime(2023, 10, 26, 9, 0, 0) # Fixed time for reproducibility

        # mock_schedule_failsafe_data already creates a structure for a single agent
        # where schedule_daily has "failed" (returned empty dict).
        # It assumes wake_up is 8 AM.
        checkpoint1_raw = mock_schedule_failsafe_data(agent_name, current_time.strftime("%Y%m%d-%H:%M"))
        # Add stride to the checkpoint data as get_stride_from_checkpoints expects it
        checkpoint1_raw["stride"] = 10

        # _process_checkpoints_to_movement_data expects a list of loaded checkpoint dicts
        checkpoint_data_list = [checkpoint1_raw["agents"][agent_name]]
        # Correction: _process_checkpoints_to_movement_data expects list of FULL checkpoint dicts
        checkpoint_data_list = [checkpoint1_raw]


        conversation_content = {}
        maze_instance = MockMaze()

        result = _process_checkpoints_to_movement_data(
            checkpoint_data_list,
            conversation_content,
            mock_static_agent_data_loader,
            maze_instance
        )

        # Assertions on result:
        self.assertIn(agent_name, result["persona_init_pos"])
        initial_pos_from_static = mock_static_agent_data_loader(agent_name)["coord"]
        self.assertEqual(result["persona_init_pos"][agent_name], initial_pos_from_static)

        # Check Frame 0 (initial state)
        self.assertIn("0", result["all_movement"])
        self.assertIn(agent_name, result["all_movement"]["0"])
        frame0_agent_data = result["all_movement"]["0"][agent_name]
        self.assertEqual(frame0_agent_data["description"], "正在睡觉")
        self.assertEqual(frame0_agent_data["movement"], initial_pos_from_static)

        # Expected location for frame 0 (living_area from static data)
        static_data = mock_static_agent_data_loader(agent_name)
        expected_location_frame0 = get_location(static_data["spatial"]["address"]["living_area"])
        self.assertEqual(frame0_agent_data["location"], expected_location_frame0)

        # Check frames generated from checkpoint1_data (step 1)
        # These frames should be 1 to FRAMES_PER_STEP
        # Since schedule_daily failsafed (empty dict), the agent's schedule beyond waking up is empty.
        # The current logic in compress.py might have the agent continue "睡觉" if no other task,
        # or it might default to the "currently" status if the action description is empty.
        # Based on mock_schedule_failsafe_data, the daily_schedule list only contains "睡觉".
        # The processing loop in _process_checkpoints_to_movement_data for step 1
        # will use the 'action' from the checkpoint data. In mock_schedule_failsafe_data,
        # the agent's 'action' field in the checkpoint itself is not defined.
        # Let's refine mock_schedule_failsafe_data to include a minimal action reflecting the schedule.

        # If the schedule only has "睡觉", the action derived in the simulation for step 1 would be "睡觉".
        # The `agent_data["action"]["event"]["describe"]` in `_process_checkpoints_to_movement_data`
        # would be "睡觉".

        # Let's assume the checkpoint data for agent_name reflects this "睡觉" action.
        # We need to ensure `checkpoint1_raw["agents"][agent_name]` has an appropriate "action" field.
        if "action" not in checkpoint1_raw["agents"][agent_name]:
             checkpoint1_raw["agents"][agent_name]["action"] = {
                "event": {
                    "subject": agent_name, "predicate": "正在", "object": "睡觉",
                    "describe": "睡觉", # Or f"{agent_name} 正在 睡觉"
                    "address": static_data["spatial"]["address"]["living_area"], # Bed location
                    "emoji": "😴"
                },
                 "obj_event": None # Or a minimal object event for the bed
            }

        # Re-run with updated checkpoint data that includes action
        # (This is a bit of a hack; ideally the mock data function is complete)
        # Re-creating the list as the dict was modified.
        checkpoint_data_list = [checkpoint1_raw]
        result = _process_checkpoints_to_movement_data(
            checkpoint_data_list, conversation_content, mock_static_agent_data_loader, maze_instance
        )

        for i in range(FRAMES_PER_STEP):
            frame_key = str(i + 1) # Frames 1 to FRAMES_PER_STEP
            self.assertIn(frame_key, result["all_movement"])
            self.assertIn(agent_name, result["all_movement"][frame_key])

            frame_agent_data = result["all_movement"][frame_key][agent_name]
            # Agent should remain at their initial position (bed) and be sleeping
            self.assertEqual(frame_agent_data["movement"], initial_pos_from_static)
            self.assertEqual(frame_agent_data["location"], expected_location_frame0)
            self.assertTrue("睡觉" in frame_agent_data["action"]) # Action description


class TestCompressWithFailsafeAction(unittest.TestCase):
    def test_process_action_failsafe_data(self):
        agent_name = "TestAgentAction"
        current_time = datetime(2023, 10, 27, 10, 0, 0)

        checkpoint1_raw = mock_action_failsafe_data(agent_name, current_time.strftime("%Y%m%d-%H:%M"))
        checkpoint1_raw["stride"] = 15 # Add stride
        checkpoint_data_list = [checkpoint1_raw]

        conversation_content = {}
        maze_instance = MockMaze()

        # For this test, ensure the static data has a different initial location than the action's failsafe location
        # to clearly distinguish them.
        custom_static_data = mock_static_agent_data_loader(agent_name)
        custom_static_data["coord"] = [5,5] # Different from action's target
        custom_static_data["spatial"]["address"]["living_area"] = ["<world>", "初始房子", "初始卧室"]

        def custom_loader(name):
            if name == agent_name:
                return custom_static_data
            return mock_static_agent_data_loader(name) # Fallback for other agents if any

        result = _process_checkpoints_to_movement_data(
            checkpoint_data_list,
            conversation_content,
            custom_loader, # Use the custom loader for this test
            maze_instance
        )

        # Frame 0 assertions
        self.assertIn(agent_name, result["persona_init_pos"])
        self.assertEqual(result["persona_init_pos"][agent_name], [5,5]) # From custom_static_data
        frame0_agent_data = result["all_movement"]["0"][agent_name]
        self.assertEqual(frame0_agent_data["description"], "正在睡觉")
        self.assertEqual(frame0_agent_data["location"], get_location(["<world>", "初始房子", "初始卧室"]))


        # Check frames from checkpoint1_data (step 1, frames 1 to FRAMES_PER_STEP)
        # The action in mock_action_failsafe_data has an address like ["<world>", "测试扇区", "测试区域", ""]
        # The object name is empty due to failsafe.
        # The obj_event description uses "空闲".
        # The agent's event description is "agent_name 此时 阅读一本有趣的书"

        expected_action_location_str = get_location(["<world>", "测试扇区", "测试区域", ""]) # "测试扇区，测试区域，"
        # The mock_action_failsafe_data defines the agent's event as trying to "阅读一本有趣的书"
        expected_action_desc_fragment = "阅读一本有趣的书" # This is from the plan, not the failsafe part of obj_event.
                                                        # The obj_event's "空闲" doesn't directly become agent's action text.

        for i in range(FRAMES_PER_STEP):
            frame_key = str(i + 1)
            self.assertIn(frame_key, result["all_movement"])
            self.assertIn(agent_name, result["all_movement"][frame_key])

            frame_agent_data = result["all_movement"][frame_key][agent_name]

            # Location should reflect the address with the empty object name
            self.assertEqual(frame_agent_data["location"], expected_action_location_str)

            # Action description should be based on the agent's event, not the object's failsafe state
            self.assertTrue(expected_action_desc_fragment in frame_agent_data["action"])

            # Movement: MockMaze returns a direct path. First frame is source, subsequent are target.
            # Source is initial_pos [5,5]. Target is checkpoint1_raw["agents"][agent_name]["coord"]
            # which is [1,1] in mock_action_failsafe_data.
            target_coord_for_action = checkpoint1_raw["agents"][agent_name]["coord"] # This is [1,1]
            if i == 0: # First frame of movement towards target
                 self.assertEqual(frame_agent_data["movement"], [5,5]) # Still at source for the very first frame of path
                 self.assertTrue(f"前往 {expected_action_location_str}" == frame_agent_data["action"] or expected_action_location_str in frame_agent_data["action"])
            else: # Subsequent frames at target (or along path if path was longer)
                 self.assertEqual(frame_agent_data["movement"], target_coord_for_action)
                 self.assertTrue(expected_action_desc_fragment in frame_agent_data["action"])


if __name__ == '__main__':
    unittest.main()
