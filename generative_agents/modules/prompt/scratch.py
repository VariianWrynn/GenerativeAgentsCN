"""generative_agents.prompt.scratch"""

import random
import datetime
import re
from string import Template

from modules import utils
from modules.memory import Event
from modules.model import parse_llm_output


class Scratch:
    def __init__(self, name, currently, config):
        self.name = name
        self.currently = currently
        self.config = config
        self.template_path = "data/prompts"

    def build_prompt(self, template, data):
        with open(f"{self.template_path}/{template}.txt", "r", encoding="utf-8") as file:
            file_content = file.read()

        template = Template(file_content)
        filled_content = template.substitute(data)

        return filled_content

    def _base_desc(self):
        return self.build_prompt(
            "base_desc",
            {
                "name": self.name,
                "age": self.config["age"],
                "innate": self.config["innate"],
                "learned": self.config["learned"],
                "lifestyle": self.config["lifestyle"],
                "daily_plan": self.config["daily_plan"],
                "date": utils.get_timer().daily_format_cn(),
                "currently": self.currently,
            }
        )

    def prompt_poignancy_event(self, event):
        prompt = self.build_prompt(
            "poignancy_event",
            {
                "base_desc": self._base_desc(),
                "agent": self.name,
                "event": event.get_describe(),
            }
        )

        default_failsafe = random.choice(list(range(1, 11))) # Ensure failsafe is 1-10

        def parsing_callback(llm_response_text):
            try:
                patterns = [
                    r"评分[:：\s]*(\d{1,2})", # Matches "评分: 10" or "评分：10" or "评分 10"
                    r"(\d{1,2})",           # Matches "10" if only number is present
                ]
                # mode="match_last" because LLM might have reasoning then the score.
                parsed_score_str = parse_llm_output(llm_response_text, patterns, mode="match_last", ignore_empty=False)

                assert parsed_score_str, "Parsed poignancy score string is empty."

                score = int(parsed_score_str)
                assert 1 <= score <= 10, f"Parsed poignancy score '{score}' out of range (1-10)."

                return score
            except (AssertionError, ValueError):
                return None # Signal retry

        return {"prompt": prompt, "callback": parsing_callback, "failsafe": default_failsafe}

    def prompt_poignancy_chat(self, event):
        prompt = self.build_prompt(
            "poignancy_chat",
            {
                "base_desc": self._base_desc(),
                "agent": self.name,
                "event": event.get_describe(),
            }
        )

        default_failsafe = random.choice(list(range(1, 11))) # Ensure failsafe is 1-10

        def parsing_callback(llm_response_text):
            try:
                patterns = [
                    r"评分[:：\s]*(\d{1,2})", # Matches "评分: 10" etc.
                    r"(\d{1,2})",           # Matches "10"
                ]
                parsed_score_str = parse_llm_output(llm_response_text, patterns, mode="match_last", ignore_empty=False)

                assert parsed_score_str, "Parsed poignancy score string for chat is empty."

                score = int(parsed_score_str)
                assert 1 <= score <= 10, f"Parsed poignancy chat score '{score}' out of range (1-10)."

                return score
            except (AssertionError, ValueError):
                return None # Signal retry

        return {"prompt": prompt, "callback": parsing_callback, "failsafe": default_failsafe}

    def prompt_wake_up(self):
        prompt = self.build_prompt(
            "wake_up",
            {
                "base_desc": self._base_desc(),
                "lifestyle": self.config["lifestyle"],
                "agent": self.name,
            }
        )

        default_failsafe = 6

        def parsing_callback(llm_response_text):
            try:
                patterns = [
                    "(\d{1,2}):00", # e.g., "08:00" or "8:00"
                    "(\d{1,2})",    # e.g., "8"
                    "\d{1,2}",      # e.g., "8" (if LLM just returns number)
                ]
                parsed_time_str = parse_llm_output(llm_response_text, patterns, ignore_empty=False)

                if not parsed_time_str:
                    assert False, "Parsed wake_up_time string is empty."

                wake_up_time = int(parsed_time_str)

                # Validate that the hour is within a reasonable range (e.g., 0-23)
                # The original code had a specific upper limit for wake_up_time.
                assert 0 <= wake_up_time <= 23, f"Parsed wake_up_time '{wake_up_time}' is not a valid hour."

                if wake_up_time > 11: # This was an existing logic constraint
                    return 11
                return wake_up_time
            except (AssertionError, ValueError): # ValueError if int(parsed_time_str) fails
                return None # Signal to LLMModel.completion to retry

        return {"prompt": prompt, "callback": parsing_callback, "failsafe": default_failsafe}

    def prompt_schedule_init(self, wake_up):
        prompt = self.build_prompt(
            "schedule_init",
            {
                "base_desc": self._base_desc(),
                "lifestyle": self.config["lifestyle"],
                "agent": self.name,
                "wake_up": wake_up,
            }
        )

        default_failsafe = [
            "早上6点起床并完成早餐的例行工作", "早上7点吃早餐", "早上8点看书",
            "中午12点吃午饭", "下午1点小睡一会儿", "晚上7点放松一下，看电视", "晚上11点睡觉",
        ]

        def parsing_callback(llm_response_text):
            try:
                patterns = [
                    "\d{1,2}\. (.*)。",
                    "\d{1,2}\. (.*)",
                    "\d{1,2}\) (.*)。",
                    "\d{1,2}\) (.*)",
                    # More general patterns if the numbering is missing
                    "^- (.*)。",
                    "^- (.*)",
                    "^(.*)。", # Captures a line ending with a period
                    "^(.*)",   # Captures a whole line
                ]
                # mode="match_all" returns a list of all non-overlapping matches.
                # Each item in the list is a tuple of captured groups if multiple groups,
                # or a string if only one group. Here, one group, so list of strings.
                parsed_schedule_items = parse_llm_output(llm_response_text, patterns, mode="match_all", ignore_empty=True)

                # Ensure we got something, e.g., at least a few schedule items
                assert parsed_schedule_items and len(parsed_schedule_items) >= 3, \
                       f"Parsed initial schedule has too few items: {len(parsed_schedule_items)}."

                return parsed_schedule_items
            except AssertionError:
                return None # Signal retry

        return {"prompt": prompt, "callback": parsing_callback, "failsafe": default_failsafe}

    def prompt_schedule_daily(self, wake_up, daily_schedule):
        hourly_schedule = ""
        for i in range(wake_up):
            hourly_schedule += f"[{i}:00] 睡觉\n"
        for i in range(wake_up, 24):
            hourly_schedule += f"[{i}:00] <活动>\n"

        prompt = self.build_prompt(
            "schedule_daily",
            {
                "base_desc": self._base_desc(),
                "agent": self.name,
                "daily_schedule": "；".join(daily_schedule),
                "hourly_schedule": hourly_schedule,
            }
        )

        failsafe = {
            "6:00": "起床并完成早晨的例行工作",
            "7:00": "吃早餐",
            "8:00": "读书",
            "9:00": "读书",
            "10:00": "读书",
            "11:00": "读书",
            "12:00": "吃午饭",
            "13:00": "小睡一会儿",
            "14:00": "小睡一会儿",
            "15:00": "小睡一会儿",
            "16:00": "继续工作",
            "17:00": "继续工作",
            "18:00": "回家",
            "19:00": "放松，看电视",
            "20:00": "放松，看电视",
            "21:00": "睡前看书",
            "22:00": "准备睡觉",
            "23:00": "睡觉",
        }

        def _callback(response):
        # failsafe is already defined before this snippet in the original code

        def parsing_callback(llm_response_text):
            try:
                patterns = [
                    r"\[(\d{1,2}:\d{2})\] " + re.escape(self.name) + r"(.*)。",
                    r"\[(\d{1,2}:\d{2})\] " + re.escape(self.name) + r"(.*)",
                    r"\[(\d{1,2}:\d{2})\] (.*)。", # Simpler if name is not included
                    r"\[(\d{1,2}:\d{2})\] (.*)",   # Simpler if name is not included
                ]
                # mode="match_all" returns a list of tuples, where each tuple contains (time_str, activity_str)
                outputs = parse_llm_output(llm_response_text, patterns, mode="match_all", ignore_empty=True)

                assert outputs and len(outputs) >= 5, \
                       f"Parsed daily schedule has too few items: {len(outputs)}. Got: {outputs}"

                # Convert list of (time_str, activity_str) tuples to dict {time_str: activity_str}
                schedule_dict = {s[0]: s[1].strip() for s in outputs}

                # Optional: Further validation on schedule_dict keys/values if needed
                assert len(schedule_dict) >= 5, \
                       f"Constructed schedule dictionary has too few unique time entries: {len(schedule_dict)}"

                return schedule_dict
            except AssertionError:
                return None # Signal retry
            except Exception: # Catch any other potential errors during processing (e.g. s[0], s[1] access)
                return None


        return {"prompt": prompt, "callback": parsing_callback, "failsafe": failsafe}

    def prompt_schedule_decompose(self, plan, schedule):
        def _plan_des(plan):
            start, end = schedule.plan_stamps(plan, time_format="%H:%M")
            return f'{start} 至 {end}，{self.name} 计划 {plan["describe"]}'

        indices = range(
            max(plan["idx"] - 1, 0), min(plan["idx"] + 2, len(schedule.daily_schedule))
        )

        start, end = schedule.plan_stamps(plan, time_format="%H:%M")
        increment = max(int(plan["duration"] / 100) * 5, 5)

        prompt = self.build_prompt(
            "schedule_decompose",
            {
                "base_desc": self._base_desc(),
                "agent": self.name,
                "plan": "；".join([_plan_des(schedule.daily_schedule[i]) for i in indices]),
                "increment": increment,
                "start": start,
                "end": end,
            }
        )

        default_failsafe = [(plan["describe"], 10) for _ in range(int(plan["duration"] / 10))]

        def parsing_callback(llm_response_text):
            try:
                patterns = [
                    # Matches "1) *计划* activity (耗时: 10, 剩余: 0)" - note the flexible spaces and punctuation
                    r"\d{1,2}\)\s*\*计划\*\s*(.*?)[\(（]\s*耗时[:：\s]*(\d{1,2})\s*[,，\s]*剩余[:：\s]*\d*\s*[\)）]",
                ]
                # mode="match_all" returns list of (activity_str, duration_str) tuples
                parsed_outputs = parse_llm_output(llm_response_text, patterns, mode="match_all", ignore_empty=True)

                assert parsed_outputs, "No schedule items parsed for decompose."

                schedules = []
                total_parsed_duration = 0
                for item_activity, item_duration_str in parsed_outputs:
                    item_duration = int(item_duration_str) # Can raise ValueError
                    schedules.append((item_activity.strip("."), item_duration))
                    total_parsed_duration += item_duration

                # Ensure total duration from parsed items is reasonable, e.g., not vastly exceeding original plan
                # This is a soft check; primary goal is parsing.
                # assert total_parsed_duration <= plan["duration"] * 1.5, "Total duration of decomposed items exceeds plan."

                left = plan["duration"] - total_parsed_duration
                if left > 0:
                    schedules.append((plan["describe"], left))

                assert schedules, "Resulting schedule list is empty after processing." # Should have at least one item
                return schedules
            except (AssertionError, ValueError): # ValueError from int()
                return None # Signal retry

        return {"prompt": prompt, "callback": parsing_callback, "failsafe": default_failsafe}

    def prompt_schedule_revise(self, action, schedule):
        plan, _ = schedule.current_plan()
        start, end = schedule.plan_stamps(plan, time_format="%H:%M")
        act_start_minutes = utils.daily_duration(action.start)
        original_plan, new_plan = [], []

        def _plan_des(start, end, describe):
            if not isinstance(start, str):
                start = start.strftime("%H:%M")
            if not isinstance(end, str):
                end = end.strftime("%H:%M")
            return "[{} 至 {}] {}".format(start, end, describe)

        for de_plan in plan["decompose"]:
            de_start, de_end = schedule.plan_stamps(de_plan, time_format="%H:%M")
            original_plan.append(_plan_des(de_start, de_end, de_plan["describe"]))
            if de_plan["start"] + de_plan["duration"] <= act_start_minutes:
                new_plan.append(_plan_des(de_start, de_end, de_plan["describe"]))
            elif de_plan["start"] <= act_start_minutes:
                new_plan.extend(
                    [
                        _plan_des(de_start, action.start, de_plan["describe"]),
                        _plan_des(
                            action.start, action.end, action.event.get_describe(False)
                        ),
                    ]
                )

        original_plan, new_plan = "\n".join(original_plan), "\n".join(new_plan)

        prompt = self.build_prompt(
            "schedule_revise",
            {
                "agent": self.name,
                "start": start,
                "end": end,
                "original_plan": original_plan,
                "duration": action.duration,
                "event": action.event.get_describe(),
                "new_plan": new_plan,
            }
        )

        default_failsafe = plan["decompose"] # Original decomposed plan as failsafe

        def parsing_callback(llm_response_text):
            try:
                patterns = [
                    r"^\[(\d{1,2}:\d{1,2})\s*-\s*(\d{1,2}:\d{1,2})\]\s*(.*)",
                    r"^\[(\d{1,2}:\d{1,2})\s*~\s*(\d{1,2}:\d{1,2})\]\s*(.*)",
                    r"^\[(\d{1,2}:\d{1,2})\s*至\s*(\d{1,2}:\d{1,2})\]\s*(.*)",
                ]
                # mode="match_all" returns list of (start_str, end_str, describe_str) tuples
                parsed_schedules = parse_llm_output(llm_response_text, patterns, mode="match_all", ignore_empty=True)

                assert parsed_schedules, "No schedule items parsed for revise."

                decomposed_result = []
                for idx, item_tuple in enumerate(parsed_schedules):
                    assert len(item_tuple) == 3, f"Parsed schedule item is not a 3-tuple: {item_tuple}"
                    start_str, end_str, describe_str = item_tuple

                    m_start = utils.daily_duration(utils.to_date(start_str, "%H:%M")) # Can raise ValueError
                    m_end = utils.daily_duration(utils.to_date(end_str, "%H:%M"))   # Can raise ValueError

                    duration = m_end - m_start
                    assert duration >= 0, f"Negative duration calculated for item: {describe_str}"

                    decomposed_result.append({
                        "idx": idx, # Use current index, original idx might not be relevant after revision
                        "describe": describe_str.strip(),
                        "start": m_start,
                        "duration": duration,
                    })

                assert decomposed_result, "Resulting revised schedule is empty after processing."
                return decomposed_result
            except (AssertionError, ValueError, TypeError, IndexError): # Catch various parsing/conversion errors
                return None # Signal retry

        return {"prompt": prompt, "callback": parsing_callback, "failsafe": default_failsafe}

    def prompt_determine_sector(self, describes, spatial, address, tile):
        live_address = spatial.find_address("living_area", as_list=True)[:-1]
        curr_address = tile.get_address("sector", as_list=True)

        prompt = self.build_prompt(
            "determine_sector",
            {
                "agent": self.name,
                "live_sector": live_address[-1],
                "live_arenas": ", ".join(i for i in spatial.get_leaves(live_address)),
                "current_sector": curr_address[-1],
                "current_arenas": ", ".join(i for i in spatial.get_leaves(curr_address)),
                "daily_plan": self.config["daily_plan"],
                "areas": ", ".join(i for i in spatial.get_leaves(address)),
                "complete_plan": describes[0],
                "decomposed_plan": describes[1],
            }
        )

        sectors = spatial.get_leaves(address)
        arenas = {}
        for sec in sectors:
            arenas.update(
                {a: sec for a in spatial.get_leaves(address + [sec]) if a not in arenas}
            )
        failsafe = random.choice(sectors) # This is the ultimate failsafe if callback returns None after retries

        def parsing_callback(llm_response_text):
            try:
                patterns = [
                    ".*应该去[:： ]*(.*)。",
                    ".*应该去[:： ]*(.*)",
                    "(.+)。", # Less specific, more likely to match something
                    "(.+)",  # Even less specific
                ]
                # mode defaults to 'match_first_group_in_first_pattern'
                raw_sector = parse_llm_output(llm_response_text, patterns, ignore_empty=False)

                if not raw_sector: # If parse_llm_output returns empty string
                    assert False, "Parsed sector is empty."

                if raw_sector in sectors:
                    return raw_sector
                if raw_sector in arenas: # arenas maps arenas back to sectors
                    return arenas[raw_sector]
                # Check if the parsed output is a substring of any valid sector (e.g. LLM says "village shop" but sector is "shop")
                # This might be too lenient, but let's try a more direct match first.
                # More robust: check if the response *contains* a valid sector, but parse_llm_output with greedy patterns should handle this.
                for s_check in sectors: # Check if the raw_sector is a valid sector name, even if LLM included extra words
                    if s_check in raw_sector: # e.g. raw_sector = "the Oak Hill Cafe" and s_check = "Oak Hill Cafe"
                                            # This logic is now implicitly handled by parse_llm_output if patterns are good.
                                            # The original patterns are quite greedy.
                        # The previous patterns were designed to extract the core part.
                        # If raw_sector itself is not in `sectors` or `arenas` keys, it's a problem.
                        pass # Let it fall through to the assert if not directly in sectors or arenas keys

                # If raw_sector is not directly a key in sectors or arenas (mapping to a sector),
                # and not a superstring that got correctly parsed by a greedy pattern,
                # then it's a failure for our specific validation.
                assert False, f"Parsed sector '{raw_sector}' not in valid sectors or arena mappings."

            except AssertionError:
                return None # Signal to LLMModel.completion to retry

        return {"prompt": prompt, "callback": parsing_callback, "failsafe": failsafe}

    def prompt_determine_arena(self, describes, spatial, address):
        prompt = self.build_prompt(
            "determine_arena",
            {
                "agent": self.name,
                "target_sector": address[-1],
                "target_arenas": ", ".join(i for i in spatial.get_leaves(address)),
                "daily_plan": self.config["daily_plan"],
                "complete_plan": describes[0],
                "decomposed_plan": describes[1],
            }
        )

        arenas = spatial.get_leaves(address)
        failsafe = random.choice(arenas) # Ultimate failsafe

        def parsing_callback(llm_response_text):
            try:
                patterns = [
                    ".*应该去[:： ]*(.*)。",
                    ".*应该去[:： ]*(.*)",
                    "(.+)。",
                    "(.+)",
                ]
                # mode defaults to 'match_first_group_in_first_pattern'
                parsed_arena = parse_llm_output(llm_response_text, patterns, ignore_empty=False)

                if not parsed_arena:
                    assert False, "Parsed arena is empty."

                if parsed_arena in arenas:
                    return parsed_arena

                # Add more sophisticated checks if needed, e.g., if LLM adds extra words.
                # For now, require a direct match after parsing.
                assert False, f"Parsed arena '{parsed_arena}' not in valid arenas."

            except AssertionError:
                return None # Signal retry

        return {"prompt": prompt, "callback": parsing_callback, "failsafe": failsafe}

    def prompt_determine_object(self, describes, spatial, address):
        objects = spatial.get_leaves(address)

        prompt = self.build_prompt(
            "determine_object",
            {
                "activity": describes[1],
                "objects": ", ".join(objects),
            }
        )

        failsafe = random.choice(objects) # Ultimate failsafe

        def parsing_callback(llm_response_text):
            try:
                patterns = [
                    ".*是[:： ]*(.*)。",
                    ".*是[:： ]*(.*)",
                    "(.+)。",
                    "(.+)",
                ]
                # mode defaults to 'match_first_group_in_first_pattern'
                parsed_object = parse_llm_output(llm_response_text, patterns, ignore_empty=False)

                if not parsed_object:
                    assert False, "Parsed object is empty."

                if parsed_object in objects:
                    return parsed_object

                # Fallback: check if any of the known objects is a substring of the parsed_object
                # This handles cases like "the old bookshelf" when "bookshelf" is a known object.
                for known_obj in objects:
                    if known_obj in parsed_object:
                        return known_obj # Return the known object name

                assert False, f"Parsed object '{parsed_object}' not in or does not contain any valid objects."
            except AssertionError:
                return None # Signal retry

        return {"prompt": prompt, "callback": parsing_callback, "failsafe": failsafe}

    def prompt_describe_emoji(self, describe):
        prompt = self.build_prompt(
            "describe_emoji",
            {
                "action": describe,
            }
        )

        def _callback(response):
            # 正则表达式：匹配大多数emoji
            emoji_pattern = u"([\U0001F600-\U0001F64F]|"   # 表情符号
            emoji_pattern += u"[\U0001F300-\U0001F5FF]|"   # 符号和图标
            emoji_pattern += u"[\U0001F680-\U0001F6FF]|"   # 运输和地图符号
            emoji_pattern += u"[\U0001F700-\U0001F77F]|"   # 午夜符号
            emoji_pattern += u"[\U0001F780-\U0001F7FF]|"   # 英镑符号
            emoji_pattern += u"[\U0001F800-\U0001F8FF]|"   # 合成扩展
            emoji_pattern += u"[\U0001F900-\U0001F9FF]|"   # 补充符号和图标
            emoji_pattern += u"[\U0001FA00-\U0001FA6F]|"   # 补充符号和图标
            emoji_pattern += u"[\U0001FA70-\U0001FAFF]|"   # 补充符号和图标
            emoji_pattern += u"[\U00002702-\U000027B0]+)"  # 杂项符号

            emoji = re.compile(emoji_pattern, flags=re.UNICODE).findall(response)
            if len(emoji) > 0:
                response = "Emoji: " + "".join(i for i in emoji)
            else:
                response = ""

            return parse_llm_output(response, ["Emoji: (.*)"])[:3]

        return {"prompt": prompt, "callback": _callback, "failsafe": "💭", "retry": 1}

    def prompt_describe_event(self, subject, describe, address, emoji=None):
        prompt = self.build_prompt(
            "describe_event",
            {
                "action": describe,
            }
        )

        e_describe = describe.replace("(", "").replace(")", "").replace("<", "").replace(">", "")
        if e_describe.startswith(subject + "此时"):
            e_describe = e_describe.replace(subject + "此时", "")
        failsafe = Event(
            subject, "此时", e_describe, describe=describe, address=address, emoji=emoji
        )

        def _callback(response):
            response_list = response.replace(")", ")\n").split("\n")
            for response in response_list:
                if len(response.strip()) < 7:
                    continue
                if response.count("(") > 1 or response.count(")") > 1 or response.count("（") > 1 or response.count("）") > 1:
                    continue

                patterns = [
                    "[\(（]<(.+?)>[,， ]+<(.+?)>[,， ]+<(.*)>[\)）]",
                    "[\(（](.+?)[,， ]+(.+?)[,， ]+(.*)[\)）]",
                ]
                outputs = parse_llm_output(response, patterns)
                if len(outputs) == 3:
                    return Event(*outputs, describe=describe, address=address, emoji=emoji)

            return None

        return {"prompt": prompt, "callback": _callback, "failsafe": failsafe}

    def prompt_describe_object(self, obj, describe):
        prompt = self.build_prompt(
            "describe_object",
            {
                "object": obj,
                "agent": self.name,
                "action": describe,
            }
        )

        default_failsafe = "空闲"

        def parsing_callback(llm_response_text):
            try:
                patterns = [
                    "<" + obj + "> ?" + "(.*)。", # Matches "obj_name is state."
                    "<" + obj + "> ?" + "(.*)",   # Matches "obj_name is state"
                    # Broader patterns if the LLM doesn't use the <obj> tag:
                    obj + "现在是?" + "(.*)。", # Matches "obj_name is now state."
                    obj + "现在是?" + "(.*)",   # Matches "obj_name is now state"
                    obj + "是?" + "(.*)。",     # Matches "obj_name is state."
                    obj + "是?" + "(.*)",       # Matches "obj_name is state"
                ]
                # mode defaults to 'match_first_group_in_first_pattern'
                parsed_description = parse_llm_output(llm_response_text, patterns, ignore_empty=False)

                if not parsed_description: # If parse_llm_output returns empty
                    # Try a very generic parse if specific ones fail, though this might be too loose
                    # For object description, an empty string might be acceptable if LLM provides nothing meaningful
                    # However, to ensure some output or trigger retry for better output:
                    assert False, f"Parsed description for object '{obj}' is empty."

                return parsed_description.strip()
            except AssertionError:
                return None # Signal retry

        return {"prompt": prompt, "callback": parsing_callback, "failsafe": default_failsafe}

    def prompt_decide_chat(self, agent, other, focus, chats):
        def _status_des(a):
            event = a.get_event()
            if a.path:
                return f"{a.name} 正去往 {event.get_describe(False)}"
            return event.get_describe()

        context = "。".join(
            [c.describe for c in focus["events"]]
        )
        context += "\n" + "。".join([c.describe for c in focus["thoughts"]])
        date_str = utils.get_timer().get_date("%Y-%m-%d %H:%M:%S")
        chat_history = ""
        if chats:
            chat_history = f" {agent.name} 和 {other.name} 上次在 {chats[0].create} 聊过关于 {chats[0].describe} 的话题"
        a_des, o_des = _status_des(agent), _status_des(other)

        prompt = self.build_prompt(
            "decide_chat",
            {
                "context": context,
                "date": date_str,
                "chat_history": chat_history,
                "agent_status": a_des,
                "another_status": o_des,
                "agent": agent.name,
                "another": other.name,
            }
        )

        def _callback(response):
            if "No" in response or "no" in response or "否" in response or "不" in response:
                return False
            return True

        return {"prompt": prompt, "callback": _callback, "failsafe": False}

    def prompt_decide_chat_terminate(self, agent, other, chats):
        conversation = "\n".join(["{}: {}".format(n, u) for n, u in chats])
        conversation = (
            conversation or "[对话尚未开始]"
        )

        prompt = self.build_prompt(
            "decide_chat_terminate",
            {
                "conversation": conversation,
                "agent": agent.name,
                "another": other.name,
            }
        )

        def _callback(response):
            if "No" in response or "no" in response or "否" in response or "不" in response:
                return False
            return True

        return {"prompt": prompt, "callback": _callback, "failsafe": False}

    def prompt_decide_wait(self, agent, other, focus):
        example1 = self.build_prompt(
            "decide_wait_example",
            {
                "context": "简是丽兹的室友。2022-10-25 07:05，简和丽兹互相问候了早上好。",
                "date": "2022-10-25 07:09",
                "agent": "简",
                "another": "丽兹",
                "status": "简 正要去浴室",
                "another_status": "丽兹 已经在 使用浴室",
                "action": "使用浴室",
                "another_action": "使用浴室",
                "reason": "推理：简和丽兹都想用浴室。简和丽兹同时使用浴室会很奇怪。所以，既然丽兹已经在用浴室了，对简来说最好的选择就是等着用浴室。\n",
                "answer": "答案：<选项A>",
            }
        )
        example2 = self.build_prompt(
            "decide_wait_example",
            {
                "context": "山姆是莎拉的朋友。2022-10-24 23:00，山姆和莎拉就最喜欢的电影进行了交谈。",
                "date": "2022-10-25 12:40",
                "agent": "山姆",
                "another": "莎拉",
                "status": "山姆 正要去吃午饭",
                "another_status": "莎拉 已经在 洗衣服",
                "action": "吃午饭",
                "another_action": "洗衣服",
                "reason": "推理：山姆可能会在餐厅吃午饭。莎拉可能会去洗衣房洗衣服。由于山姆和莎拉需要使用不同的区域，他们的行为并不冲突。所以，由于山姆和莎拉将在不同的区域，山姆现在继续吃午饭。\n",
                "answer": "答案：<选项B>",
            }
        )

        def _status_des(a):
            event, loc = a.get_event(), ""
            if event.address:
                loc = " 在 {} 的 {}".format(event.address[-2], event.address[-1])
            if not a.path:
                return f"{a.name} 已经在 {event.get_describe(False)}{loc}"
            return f"{a.name} 正要去 {event.get_describe(False)}{loc}"

        context = ". ".join(
            [c.describe for c in focus["events"]]
        )
        context += "\n" + ". ".join([c.describe for c in focus["thoughts"]])

        task = self.build_prompt(
            "decide_wait_example",
            {
                "context": context,
                "date": utils.get_timer().get_date("%Y-%m-%d %H:%M"),
                "agent": agent.name,
                "another": other.name,
                "status": _status_des(agent),
                "another_status": _status_des(other),
                "action": agent.get_event().get_describe(False),
                "another_action": other.get_event().get_describe(False),
                "reason": "",
                "answer": "",
            }
        )

        prompt = self.build_prompt(
            "decide_wait",
            {
                "examples_1": example1,
                "examples_2": example2,
                "task": task,
            }
        )

        def _callback(response):
            return "A" in response

        return {"prompt": prompt, "callback": _callback, "failsafe": False}

    def prompt_summarize_relation(self, agent, other_name):
        nodes = agent.associate.retrieve_focus([other_name], 50)

        prompt = self.build_prompt(
            "summarize_relation",
            {
                "context": "\n".join(["{}. {}".format(idx, n.describe) for idx, n in enumerate(nodes)]),
                "agent": agent.name,
                "another": other_name,
            }
        )

        default_failsafe = agent.name + " 正在看着 " + other_name

        def parsing_callback(llm_response_text):
            try:
                parsed_relation = llm_response_text.strip()
                assert parsed_relation, "Summarized relation is empty."
                return parsed_relation
            except AssertionError:
                return None # Signal retry

        return {"prompt": prompt, "callback": parsing_callback, "failsafe": default_failsafe}

    def prompt_generate_chat(self, agent, other, relation, chats):
        focus = [relation, other.get_event().get_describe()]
        if len(chats) > 4:
            focus.append("; ".join("{}: {}".format(n, t) for n, t in chats[-4:]))
        nodes = agent.associate.retrieve_focus(focus, 15)
        memory = "\n- " + "\n- ".join([n.describe for n in nodes])
        chat_nodes = agent.associate.retrieve_chats(other.name)
        pass_context = ""
        for n in chat_nodes:
            delta = utils.get_timer().get_delta(n.create)
            if delta > 480:
                continue
            pass_context += f"{delta} 分钟前，{agent.name} 和 {other.name} 进行过对话。{n.describe}\n"

        address = agent.get_tile().get_address()
        if len(pass_context) > 0:
            prev_context = f'\n背景：\n"""\n{pass_context}"""\n\n'
        else:
            prev_context = ""
        curr_context = (
            f"{agent.name} {agent.get_event().get_describe(False)} 时，看到 {other.name} {other.get_event().get_describe(False)}。"
        )

        conversation = "\n".join(["{}: {}".format(n, u) for n, u in chats])
        conversation = (
            conversation or "[对话尚未开始]"
        )

        prompt = self.build_prompt(
            "generate_chat",
            {
                "agent": agent.name,
                "base_desc": self._base_desc(),
                "memory": memory,
                "address": f"{address[-2]}，{address[-1]}",
                "current_time": utils.get_timer().get_date("%H:%M"),
                "previous_context": prev_context,
                "current_context": curr_context,
                "another": other.name,
                "conversation": conversation,
            }
        )

        default_failsafe = "嗯"

        # This specific callback needs `agent` from the outer scope for json_content[agent.name]
        # So, we pass it to the parsing_callback_factory or define parsing_callback inside prompt_generate_chat

        def parsing_callback(llm_response_text):
            try:
                # Ensure the response contains a parsable JSON block for the agent's speech.
                # The original code expects something like "... { "AgentName": "Speech content..." } ..."
                # A more robust way to find the JSON block might be needed if the LLM is inconsistent.
                # For now, stick to the original logic of finding the first '{' and last '}'.

                first_brace = llm_response_text.find("{")
                last_brace = llm_response_text.rfind("}")

                assert first_brace != -1 and last_brace != -1 and last_brace > first_brace, \
                    f"Valid JSON block not found in response: {llm_response_text[:100]}"

                json_str_to_parse = llm_response_text[first_brace : last_brace + 1]

                # utils.load_dict might be a custom JSON loader; assume it can raise json.JSONDecodeError or similar
                json_content = utils.load_dict(json_str_to_parse)

                # agent.name is from the outer scope of prompt_generate_chat
                assert agent.name in json_content, f"Agent name '{agent.name}' not in parsed JSON keys: {list(json_content.keys())}"

                text = json_content[agent.name]
                assert isinstance(text, str), "Parsed chat content is not a string."

                text = text.replace("\n\n", "\n").strip(" \n\"'“”‘’")
                assert text, "Generated chat text is empty after stripping."

                return text
            except (AssertionError, json.JSONDecodeError, KeyError, IndexError): # Added IndexError for split issues if that was used
                return None # Signal retry

        return {"prompt": prompt, "callback": parsing_callback, "failsafe": default_failsafe}

    def prompt_generate_chat_check_repeat(self, agent, chats, content):
        conversation = "\n".join(["{}: {}".format(n, u) for n, u in chats])
        conversation = (
                conversation or "[对话尚未开始]"
        )

        prompt = self.build_prompt(
            "generate_chat_check_repeat",
            {
                "conversation": conversation,
                "content": f"{agent.name}: {content}",
                "agent": agent.name,
            }
        )

        def _callback(response):
            if "No" in response or "no" in response or "否" in response or "不" in response:
                return False
            return True

        return {"prompt": prompt, "callback": _callback, "failsafe": False}

    def prompt_summarize_chats(self, chats):
        conversation = "\n".join(["{}: {}".format(n, u) for n, u in chats])

        prompt = self.build_prompt(
            "summarize_chats",
            {
                "conversation": conversation,
            }
        )

        if len(chats) > 1:
            default_failsafe = "{} 和 {} 之间的普通对话".format(chats[0][0], chats[1][0])
        else:
            default_failsafe = "{} 说的话没有得到回应".format(chats[0][0])

        def parsing_callback(llm_response_text):
            try:
                parsed_summary = llm_response_text.strip()
                assert parsed_summary, "Summarized chat is empty."
                return parsed_summary
            except AssertionError:
                return None # Signal retry

        return {"prompt": prompt, "callback": parsing_callback, "failsafe": default_failsafe}

    def prompt_reflect_focus(self, nodes, topk):
        prompt = self.build_prompt(
            "reflect_focus",
            {
                "reference": "\n".join(["{}. {}".format(idx, n.describe) for idx, n in enumerate(nodes)]),
                "number": topk,
            }
        )

        default_failsafe = [
            "{} 是谁？".format(self.name), "{} 住在哪里？".format(self.name),
            "{} 今天要做什么？".format(self.name),
        ]

        def parsing_callback(llm_response_text):
            try:
                patterns = [
                    r"^\d{1}\.\s*(.*)", # Matches "1. text"
                    r"^\d{1}\)\s*(.*)", # Matches "1) text"
                    r"^\d{1}\s+(.*)",   # Matches "1 text" (less common)
                    r"^-\s*(.*)",       # Matches "- text"
                ]
                # mode="match_all" returns a list of strings
                parsed_focus_list = parse_llm_output(llm_response_text, patterns, mode="match_all", ignore_empty=True)

                processed_list = [item.strip() for item in parsed_focus_list if item.strip()]

                assert processed_list, \
                       f"Parsed reflect focus list is empty after processing. Raw: {llm_response_text[:300]}"

                return processed_list
            except AssertionError:
                return None # Signal retry

        return {"prompt": prompt, "callback": parsing_callback, "failsafe": default_failsafe}

    def prompt_reflect_insights(self, nodes, topk):
        prompt = self.build_prompt(
            "reflect_insights",
            {
                "reference": "\n".join(["{}. {}".format(idx, n.describe) for idx, n in enumerate(nodes)]),
                "number": topk,
            }
        )

        default_failsafe = [[f"{self.name} 在考虑下一步该做什么", [nodes[0].node_id if nodes else ""]]]

        def parsing_callback(llm_response_text):
            try:
                patterns = [
                    # Matches "1. Insight text (序号: 1, 2, 3)" or "1. Insight text (1, 2, 3)"
                    # Made insight part non-greedy (.*?) and node_indices_str greedy ([\d,\s，]+)
                    r"^\d{1}[\.\s]+(.*?)[.。\s]*[\(（]\s*(?:.*序号[:：\s]*)?([\d,\s，]+)[\)）]",
                ]
                # mode="match_all" returns list of (insight_str, node_indices_str) tuples
                parsed_outputs = parse_llm_output(llm_response_text, patterns, mode="match_all", ignore_empty=True)

                assert parsed_outputs, f"No insights parsed from text: {llm_response_text[:500]}"

                insights_result = []
                for output_tuple in parsed_outputs:
                    # Ensure output_tuple is a tuple and has at least 2 elements, though pattern implies exactly 2.
                    if not (isinstance(output_tuple, (list, tuple)) and len(output_tuple) == 2):
                        # Log or handle malformed tuple if necessary, then skip or assert
                        # For now, we'll be strict and expect parse_llm_output to give correct tuples based on pattern.
                        # This could be an assertion failure if a specific tuple structure is critical.
                        # However, parse_llm_output for 'match_all' with groups returns list of tuples of strings.
                        # If a match occurs but a group is empty, it's an empty string.
                        pass # Let it proceed, subsequent code might fail if parts are empty where not expected.


                    insight_str, node_indices_str = output_tuple
                    insight_text = insight_str.strip()

                    processed_node_ids = []
                    if node_indices_str: # Check if node_indices_str is not empty
                        try:
                            # Split by comma or space, handling Chinese comma as well
                            indices_str_list = re.split(r'[,\s，]+', node_indices_str.strip())
                            # Filter out empty strings that might result from multiple spaces/commas
                            valid_indices_str = [s for s in indices_str_list if s.strip().isdigit()]
                            indices = [int(s) for s in valid_indices_str]
                            processed_node_ids = [nodes[i].node_id for i in indices if i < len(nodes)]
                        except ValueError:
                            # This handles if int(s) fails for a non-digit string part not filtered by isdigit
                            # (though isdigit should prevent this).
                            # Or if nodes itself is not what's expected, though that's outside parsing.
                            pass # Or log: self.logger.warning(f"Could not parse node indices: {node_indices_str}")

                    assert insight_text, "Parsed insight text is empty." # Ensure insight text itself isn't empty
                    insights_result.append([insight_text, processed_node_ids])

                assert insights_result, "Resulting insights list is empty after processing all parsed outputs."
                return insights_result
            except (AssertionError, ValueError, TypeError, IndexError): # Catch various errors
                return None # Signal retry

        return {"prompt": prompt, "callback": parsing_callback, "failsafe": default_failsafe}

    def prompt_reflect_chat_planing(self, chats):
        all_chats = "\n".join(["{}: {}".format(n, c) for n, c in chats])

        prompt = self.build_prompt(
            "reflect_chat_planing",
            {
                "conversation": all_chats,
                "agent": self.name,
            }
        )

        default_failsafe = f"{self.name} 进行了一次对话"

        def parsing_callback(llm_response_text):
            try:
                parsed_text = llm_response_text.strip()
                assert parsed_text, "Reflected chat planning is empty."
                return parsed_text
            except AssertionError:
                return None # Signal retry

        return {"prompt": prompt, "callback": parsing_callback, "failsafe": default_failsafe}

    def prompt_reflect_chat_memory(self, chats):
        all_chats = "\n".join(["{}: {}".format(n, c) for n, c in chats])

        prompt = self.build_prompt(
            "reflect_chat_memory",
            {
                "conversation": all_chats,
                "agent": self.name,
            }
        )

        default_failsafe = f"{self.name} 进行了一次对话"

        def parsing_callback(llm_response_text):
            try:
                parsed_text = llm_response_text.strip()
                assert parsed_text, "Reflected chat memory is empty."
                return parsed_text
            except AssertionError:
                return None # Signal retry

        return {"prompt": prompt, "callback": parsing_callback, "failsafe": default_failsafe}

    def prompt_retrieve_plan(self, nodes):
        statements = [
            n.create.strftime("%Y-%m-%d %H:%M") + ": " + n.describe for n in nodes
        ]

        prompt = self.build_prompt(
            "retrieve_plan",
            {
                "description": "\n".join(statements),
                "agent": self.name,
                "date": utils.get_timer().get_date("%Y-%m-%d"),
            }
        )

        default_failsafe = [r.describe for r in random.choices(nodes, k=5)]

        def parsing_callback(llm_response_text):
            try:
                patterns = [
                    r"^\d{1,2}\.\s*(.*)。?",  # Matches "1. text." or "1. text"
                    r"^\d{1,2}\)\s*(.*)。?",  # Matches "1) text." or "1) text"
                    r"^-\s*(.*)。?",        # Matches "- text." or "- text"
                    r"^(.*)。?",            # Matches "text." or "text" (as a fallback for single lines)
                ]
                # mode="match_all" returns a list of strings (first captured group from each match)
                parsed_plans = parse_llm_output(llm_response_text, patterns, mode="match_all", ignore_empty=True)

                # Filter out any potential empty strings after stripping, if any slip through ignore_empty
                # and ensure at least one valid plan item exists.
                processed_plans = [plan.strip() for plan in parsed_plans if plan.strip()]

                assert processed_plans, \
                       f"Parsed retrieved plans list is empty after processing. Raw: {llm_response_text[:300]}"

                return processed_plans
            except AssertionError:
                return None # Signal retry

        return {"prompt": prompt, "callback": parsing_callback, "failsafe": default_failsafe}

    def prompt_retrieve_thought(self, nodes):
        statements = [
            n.create.strftime("%Y-%m-%d %H:%M") + "：" + n.describe for n in nodes
        ]

        prompt = self.build_prompt(
            "retrieve_thought",
            {
                "description": "\n".join(statements),
                "agent": self.name,
            }
        )

        default_failsafe = "{} 应该遵循昨天的日程".format(self.name)

        def parsing_callback(llm_response_text):
            try:
                # Thought is often a free-form sentence or paragraph.
                # We just want to ensure it's not empty if the LLM responds.
                parsed_thought = llm_response_text.strip()

                assert parsed_thought, "Retrieved thought is empty."

                return parsed_thought
            except AssertionError:
                return None # Signal retry

        return {"prompt": prompt, "callback": parsing_callback, "failsafe": default_failsafe}

    def prompt_retrieve_currently(self, plan_note, thought_note):
        time_stamp = (
            utils.get_timer().get_date() - datetime.timedelta(days=1)
        ).strftime("%Y-%m-%d")

        prompt = self.build_prompt(
            "retrieve_currently",
            {
                "agent": self.name,
                "time": time_stamp,
                "currently": self.currently,
                "plan": ". ".join(plan_note),
                "thought": thought_note,
                "current_time": utils.get_timer().get_date("%Y-%m-%d"),
            }
        )

        default_failsafe = self.currently # Original 'currently' status as failsafe

        def parsing_callback(llm_response_text):
            try:
                patterns = [
                    r"^状态[:：\s]*(.*)。?", # Matches "状态: text." or "状态: text" with optional period
                    r"^(.*)。?",            # Fallback: matches "text." or "text" if prefix is missing
                ]
                # Expects a single string output
                parsed_currently = parse_llm_output(llm_response_text, patterns, ignore_empty=False)

                assert parsed_currently, "Parsed 'currently' status is empty."

                return parsed_currently.strip() # Return the stripped string
            except AssertionError:
                return None # Signal retry

        return {"prompt": prompt, "callback": parsing_callback, "failsafe": default_failsafe}
