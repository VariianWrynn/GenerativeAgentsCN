import unittest
import datetime # For timestamps in mock data

# Note: The actual replay.py processing logic is not directly tested here yet.
# These tests focus on defining and validating the structure of mock data
# that represents simulation states when LLM failsafe values are used.
# This helps in understanding what data replay.py would need to handle.

def mock_schedule_failsafe_data(agent_name="测试角色", current_time_str="2023-10-26 09:00:00"):
    """
    Generates mock simulation data where an agent's daily schedule part (from schedule_daily)
    has resulted in a failsafe (empty dictionary {}), meaning no tasks for the day beyond defaults.
    The schedule_init part might still succeed, and wake_up might succeed.
    The key is that `schedule_daily` failsafe (empty dict {}) means no tasks are added for the day.
    """
    # Failsafe for prompt_schedule_daily is an empty dict {}
    # Failsafe for prompt_wake_up is 6 (int)
    # Failsafe for prompt_schedule_init is a list of strings.

    # Let's assume wake_up succeeded (e.g., 8 AM) and schedule_init provided some initial tasks.
    # But schedule_daily (which fills the hourly slots) returned its failsafe (empty dict).
    # The Schedule class in memory.py would then only have tasks derived from schedule_init
    # or default sleep tasks. If schedule_daily's output is empty, the hourly schedule
    # for the day (post wake-up) might effectively be empty or only contain items from schedule_init
    # if they were directly convertible to hourly slots without schedule_daily's help.

    # In the current Schedule implementation:
    # 1. `wake_up` determines wake up hour.
    # 2. `init_schedule` gives a list of general tasks.
    # 3. `schedule_daily` tries to map these to hourly slots. If it failsafe (empty dict),
    #    the schedule `self.schedule.schedule` (which is a dict) remains empty for those hours.
    #    The `self.schedule.daily_schedule` (list of plans) will be built based on this.
    #    If `schedule_daily` failsafe (empty dict) is used, then `daily_schedule` list
    #    will only contain sleep tasks up to wake_up hour.

    wake_up_hour = 8 # Example successful wake_up

    # The schedule structure in checkpoints is usually a list of plan dicts.
    # If schedule_daily failsafes to {}, the agent's schedule for the day
    # will be just the sleep task before wake_up.
    daily_schedule_plans = []
    if wake_up_hour > 0:
        daily_schedule_plans.append({
            "idx": 0,
            "start": 0, # Midnight
            "duration": wake_up_hour * 60, # Duration in minutes
            "describe": "睡觉",
            "decompose": [] # Assuming sleep is not decomposed
        })
    # If schedule_daily provided an empty dict, no further tasks are added for the day.

    return {
        "agents": {
            agent_name: {
                "name": agent_name,
                "schedule": {
                    "create": current_time_str, # Timestamp of schedule creation
                    "daily_schedule": daily_schedule_plans,
                    "scheduled_idx": 0, # Example
                    "current_idx": 0,   # Example
                    # Other schedule fields as they appear in actual checkpoints
                },
                "coord": [0,0], # Example
                "status": {"poignancy": 0}, # Example
                # ... other agent fields
            }
        },
        "time": current_time_str,
        "step": 1, # Example
    }

def mock_action_failsafe_data(agent_name="测试角色", current_time_str="2023-10-26 10:00:00"):
    """
    Generates mock simulation data where an agent's action fields
    reflect failsafe values from determine_object and describe_object.
    - determine_object failsafe: random.choice(objects) -> let's pick a specific one or assume it's an empty string if objects list was empty or upstream failed.
                                For this test, let's assume it results in an empty string for the object name in the address.
    - describe_object failsafe: "空闲" (idle)
    """
    # Failsafe for determine_object (if it truly fails to pick one from list or list is empty) isn't explicitly empty string,
    # but if the list of objects it has to pick from is empty (e.g. due to prior sector/arena failsafe),
    # then the address part for object might be missing or empty.
    # Let's assume the object name part of the address becomes effectively empty for the event.
    # The subject of obj_event would also be this empty name.
    # The describe for obj_event would use the failsafe "空闲".

    failsafe_object_name = "" # Representing failure to determine a specific object
    failsafe_object_description = "空闲" # Failsafe for describe_object

    # If determine_object leads to an effectively empty object selection for the action's address.
    # The event's object and describe would be based on the current plan's describe,
    # but its address would reflect the failure.
    # describe_object's failsafe ("空闲") affects obj_event's description.

    # Example current plan description that agent tries to execute
    current_plan_describe = "阅读一本有趣的书"
    # Default emoji if describe_emoji also fails or not called with specific info
    default_emoji = "❓"

    return {
        "agents": {
            agent_name: {
                "name": agent_name,
                "action": {
                    "event": {
                        "subject": agent_name,
                        "predicate": "此时", # Typical for ongoing actions
                        "object": current_plan_describe, # What the agent is trying to do
                        "describe": f"{agent_name} 此时 {current_plan_describe}",
                        # Address reflects the failure to pinpoint an object
                        "address": ["<world>", "测试扇区", "测试区域", failsafe_object_name],
                        "emoji": default_emoji
                    },
                    "obj_event": { # This reflects the state of the object being interacted with
                        "subject": failsafe_object_name, # Object name is empty due to determine_object failsafe
                        "predicate": "正在被使用", # Or some other default state
                        "object": agent_name,
                        # describe_object failsafe is "空闲".
                        # The format is usually "<subject> is <description>"
                        "describe": f"{failsafe_object_name} 是 {failsafe_object_description}",
                        "address": ["<world>", "测试扇区", "测试区域", failsafe_object_name],
                        "emoji": default_emoji
                    },
                    "start": current_time_str, # Example
                    "duration": 60, # Example
                    "finished": False # Example
                },
                "coord": [1,1], # Example
                # ... other agent fields
            }
        },
        "time": current_time_str,
        "step": 2, # Example
    }


class TestFailsafeScheduleDataHandling(unittest.TestCase):
    def test_structure_schedule_with_failsafe_daily_schedule(self):
        agent_name = "约翰"
        sim_time = "2023-01-01 08:00:00"
        data = mock_schedule_failsafe_data(agent_name=agent_name, current_time_str=sim_time)

        self.assertIn("agents", data)
        self.assertIn(agent_name, data["agents"])
        agent_data = data["agents"][agent_name]
        self.assertIn("schedule", agent_data)

        schedule_data = agent_data["schedule"]
        self.assertEqual(schedule_data["create"], sim_time)
        self.assertIn("daily_schedule", schedule_data)

        # Expecting only sleep task if wake_up was e.g. 8 and schedule_daily failsafed (empty dict)
        # The mock_schedule_failsafe_data simulates wake_up at 8.
        # So, one task: sleep from 00:00 for 8*60 minutes.
        self.assertEqual(len(schedule_data["daily_schedule"]), 1)
        if schedule_data["daily_schedule"]:
            first_task = schedule_data["daily_schedule"][0]
            self.assertEqual(first_task["describe"], "睡觉")
            self.assertEqual(first_task["start"], 0) # Starts at midnight
            self.assertEqual(first_task["duration"], 8 * 60) # Duration for 8 hours of sleep

        # This test primarily validates the mock data structure.
        # Actual replay.py parsing logic would be tested separately if modular.
        # For now, we confirm the mock data reflects the intended failsafe outcome.


class TestFailsafeActionDataHandling(unittest.TestCase):
    def test_structure_action_with_failsafe_object_description(self):
        agent_name = "简"
        sim_time = "2023-01-01 10:00:00"
        data = mock_action_failsafe_data(agent_name=agent_name, current_time_str=sim_time)

        self.assertIn("agents", data)
        self.assertIn(agent_name, data["agents"])
        agent_data = data["agents"][agent_name]
        self.assertIn("action", agent_data)

        action_data = agent_data["action"]
        self.assertIn("event", action_data)
        self.assertIn("obj_event", action_data)

        agent_event = action_data["event"]
        # If determine_object failsafe led to an empty object name in address
        self.assertEqual(agent_event["address"][-1], "")
        # describe for agent's action is based on plan, not failsafe directly unless plan itself was failsafe
        # Here we assume plan was "阅读一本有趣的书"
        self.assertTrue("阅读一本有趣的书" in agent_event["describe"])

        object_event = action_data["obj_event"]
        # Subject of obj_event is the object name, which is empty due to failsafe
        self.assertEqual(object_event["subject"], "")
        # Description of obj_event uses describe_object's failsafe ("空闲")
        self.assertTrue("空闲" in object_event["describe"])
        self.assertEqual(object_event["address"][-1], "")

        # Similar to the schedule test, this validates the mock data structure
        # reflects the intended failsafe outcome for action generation.

if __name__ == '__main__':
    unittest.main()
