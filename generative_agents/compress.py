import os
import json
import argparse
from datetime import datetime

from modules.maze import Maze
from start import personas

file_markdown = "simulation.md"
file_movement = "movement.json"

frames_per_step = 60  # 每个step包含的帧数


# 从已加载的检查点数据列表中读取stride
def get_stride_from_checkpoints(checkpoint_data_list):
    if not checkpoint_data_list:
        return 1 # Default stride if no checkpoints

    # Assume the last checkpoint has the stride information
    last_checkpoint_data = checkpoint_data_list[-1]
    return last_checkpoint_data.get("stride", 1)


# 将address转换为字符串
def get_location(address):
    # 仅为兼容原版
    # if address[0] == "<waiting>" or address[0] == "<persona>":
    #     return None

    # 不需要显示address第一级（"the Ville"）
    location = "，".join(address[1:])

    return location


# 插入第0帧数据（Agent的初始状态）
def insert_frame0(init_pos, movement, agent_name, agent_static_data_content):
    key = "0"
    if key not in movement.keys():
        movement[key] = dict()

    # json_path = f"frontend/static/assets/village/agents/{agent_name}/agent.json"
    # with open(json_path, "r", encoding="utf-8") as f:
    #     json_data = json.load(f)
    #     address = json_data["spatial"]["address"]["living_area"]
    json_data = agent_static_data_content # Use passed-in content
    address = json_data["spatial"]["address"]["living_area"]
    location = get_location(address)
    coord = json_data["coord"]
    init_pos[agent_name] = coord
    movement[key][agent_name] = {
        "location": location,
        "movement": coord,
        "description": "正在睡觉", # Default initial description
    }
    movement["description"][agent_name] = {
        "currently": json_data["currently"],
        "scratch": json_data["scratch"],
    }

# Core data processing logic extracted from generate_movement
def _process_checkpoints_to_movement_data(checkpoint_data_list, conversation_content, static_agent_loader, maze_instance):
    persona_init_pos = dict()
    all_movement = dict()
    all_movement["description"] = dict()
    all_movement["conversation"] = dict()

    stride = get_stride_from_checkpoints(checkpoint_data_list)
    sec_per_step = stride # Assuming 1 step = 1 stride minute = stride seconds for simplicity here.
                         # This might need adjustment if sec_per_step is meant to be different from stride in minutes.

    result = {
        "start_datetime": "",
        "stride": stride,
        "sec_per_step": sec_per_step,
        "persona_init_pos": persona_init_pos,
        "all_movement": all_movement,
    }

    last_location = dict()
    maze = maze_instance # Use passed-in maze instance

    for json_data in checkpoint_data_list: # Iterate over loaded checkpoint data
        step = json_data["step"]
        agents = json_data["agents"]

        if not result["start_datetime"] and "time" in json_data:
            try:
                t = datetime.strptime(json_data["time"], "%Y%m%d-%H:%M")
                result["start_datetime"] = t.isoformat()
            except ValueError:
                 # Handle cases where time format might be different or missing, though unlikely for valid checkpoints
                pass


        for agent_name, agent_data in agents.items():
            if step == 1:
                agent_static_data = static_agent_loader(agent_name)
                if agent_static_data:
                    insert_frame0(persona_init_pos, all_movement, agent_name, agent_static_data)
                else:
                    # Handle missing static data if necessary, e.g., skip agent or use defaults
                    print(f"Warning: Static data for agent {agent_name} not found. Skipping frame 0 insertion.")
                    continue # Or handle more gracefully

            # Ensure frame 0 data exists for the agent before proceeding
            if agent_name not in persona_init_pos or "0" not in all_movement or agent_name not in all_movement["0"]:
                 # This can happen if the first checkpoint is not step 1, or static_agent_loader failed.
                 # For robustness, we might need to initialize last_location more carefully
                 # or ensure that step 1 always populates this.
                 # If this is critical, we might need to load static data here too if not step 1.
                 # For now, assume step 1 correctly initializes.
                 if step > 1: # If not first step and agent is missing frame 0, try to load it
                    agent_static_data = static_agent_loader(agent_name)
                    if agent_static_data:
                         insert_frame0(persona_init_pos, all_movement, agent_name, agent_static_data)
                    else: # If still can't load, skip this agent for this step
                        print(f"Warning: Agent {agent_name} missing frame 0 data at step {step}. Skipping.")
                        continue


            source_coord_data = last_location.get(agent_name, all_movement.get("0", {}).get(agent_name))
            if not source_coord_data: # If agent wasn't in frame 0 (e.g. new agent appearing later)
                # This case needs careful handling. For now, let's assume agents exist from step 1 / frame 0.
                # Or, initialize with current coord if it's their first appearance.
                print(f"Warning: Agent {agent_name} has no previous location at step {step}. Using current coord as source.")
                source_coord = agent_data["coord"]
                # Initialize last_location for this agent
                last_location[agent_name] = {"movement": source_coord, "location": get_location(agent_data.get("action", {}).get("event", {}).get("address", ["<world>"]))}

            else:
                source_coord = source_coord_data["movement"]


            target_coord = agent_data["coord"]
            action_event = agent_data.get("action", {}).get("event", {})
            location = get_location(action_event.get("address", ["<world>"])) # Default to world if no address

            if location is None or location == get_location(["<world>"]): # Check if location is placeholder or non-specific
                location = last_location.get(agent_name, {}).get("location", get_location(["<world>", "somewhere"])) # Use last known or a default
                path = [source_coord] # No actual path if location is unknown or same as last
            else:
                path = maze.find_path(source_coord, target_coord)
                if not path: # If find_path returns empty (e.g., source == target or unreachable)
                    path = [source_coord]


            had_conversation = False
            step_conversation_text = "" # Renamed to avoid conflict
            persons_in_conversation = []
            step_time = json_data["time"]

            # Use conversation_content passed as argument
            if step_time in conversation_content:
                for chats_entry in conversation_content[step_time]: # Iterate through list of conversations at this time
                    for persons, chat_log in chats_entry.items():
                        # Correctly extract agent names involved in the chat
                        chatting_pair = persons.split(" @ ")[0].split(" -> ")
                        persons_in_conversation.append(chatting_pair)
                        step_conversation_text += f"\n地点：{persons.split(' @ ')[1]}\n\n"
                        for c_agent, c_text in chat_log:
                            step_conversation_text += f"{c_agent}：{c_text}\n"

            for i in range(frames_per_step):
                moving = len(path) > 1
                current_movement_frame = None # Initialize to None

                if path: # Check if path is not empty
                    current_movement_frame = list(path[0]) # Take the current frame's movement
                    if len(path) > 1: # Only advance path if there are more steps in it
                        path = path[1:]
                    # Update last_location with the current frame's state
                    if agent_name not in last_location: last_location[agent_name] = {}
                    last_location[agent_name]["movement"] = current_movement_frame
                    last_location[agent_name]["location"] = location
                # If path was empty or became empty, current_movement_frame remains None or its last value

                action_description = ""
                if moving:
                    action_description = f"前往 {location}"
                elif current_movement_frame is not None: # Agent is at destination or was already there
                    action_description = action_event.get("describe", "")
                    if not action_description:
                        action_description = f'{action_event.get("predicate", "")}{action_event.get("object", "")}'

                    agent_had_chat_this_step = any(agent_name in pair for pair in persons_in_conversation)

                    if "睡觉" in action_description:
                        action_description = "😴 " + action_description
                    elif agent_had_chat_this_step:
                        action_description = "💬 " + action_description

                # Frame key calculation
                step_key = str((step - 1) * frames_per_step + i) # Frame 0 is handled by insert_frame0

                if step_key not in all_movement:
                    all_movement[step_key] = {}

                if current_movement_frame is not None: # Only add entry if there's movement/action
                    all_movement[step_key][agent_name] = {
                        "location": location,
                        "movement": current_movement_frame,
                        "action": action_description,
                    }
            if step_time not in all_movement["conversation"]: # Ensure key exists
                 all_movement["conversation"][step_time] = ""
            all_movement["conversation"][step_time] += step_conversation_text # Append, as multiple conversations can happen at same time step for different pairs

    return result


# 从所有存档文件中提取数据（用于回放）
def generate_movement(checkpoints_folder, compressed_folder, compressed_file_name):
    movement_file_path = os.path.join(compressed_folder, compressed_file_name)

    # Load conversation.json
    conversation_content = {}
    conversation_json_path = os.path.join(checkpoints_folder, "conversation.json")
    if os.path.exists(conversation_json_path):
        with open(conversation_json_path, "r", encoding="utf-8") as f:
            conversation_content = json.load(f)

    # Load all checkpoint JSON files
    checkpoint_data_list = []
    files = sorted(os.listdir(checkpoints_folder))
    for file_name in files:
        if file_name.endswith(".json") and file_name != "conversation.json":
            file_path = os.path.join(checkpoints_folder, file_name)
            with open(file_path, "r", encoding="utf-8") as f:
                checkpoint_data_list.append(json.load(f))

    # Sort by step to ensure chronological order
    checkpoint_data_list.sort(key=lambda cp: cp.get("step", 0))


    # Create static_agent_loader function
    def static_agent_loader(agent_name_str):
        json_path = f"frontend/static/assets/village/agents/{agent_name_str}/agent.json"
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None # Or raise an error

    # Load maze.json and instantiate Maze
    maze_json_path = "frontend/static/assets/village/maze.json"
    if not os.path.exists(maze_json_path):
        raise FileNotFoundError(f"Maze file not found: {maze_json_path}")
    with open(maze_json_path, "r", encoding="utf-8") as f:
        maze_data = json.load(f)
    maze_instance = Maze(maze_data, None) # Assuming Maze constructor takes data and optionally a logger or similar

    # Call the core processing function
    result_data = _process_checkpoints_to_movement_data(
        checkpoint_data_list,
        conversation_content,
        static_agent_loader,
        maze_instance
    )

    # Write the result to movement.json
    with open(movement_file_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2, ensure_ascii=False)

    return result_data


# 生成Markdown文档
def generate_report(checkpoints_folder, compressed_folder, compressed_file):
    last_state = dict()

    conversation_file = "conversation.json"
    conversation = {}
    if os.path.exists(os.path.join(checkpoints_folder, conversation_file)):
        with open(os.path.join(checkpoints_folder, conversation_file), "r", encoding="utf-8") as f:
            conversation = json.load(f)

    def extract_description():
        markdown_content = "# 基础人设\n\n"
        for agent_name in personas:
            json_path = f"frontend/static/assets/village/agents/{agent_name}/agent.json"
            with open(json_path, "r", encoding="utf-8") as f:
                json_data = json.load(f)
                markdown_content += f"## {agent_name}\n\n"
                markdown_content += f"年龄：{json_data['scratch']['age']}岁  \n"
                markdown_content += f"先天：{json_data['scratch']['innate']}  \n"
                markdown_content += f"后天：{json_data['scratch']['learned']}  \n"
                markdown_content += f"生活习惯：{json_data['scratch']['lifestyle']}  \n"
                markdown_content += f"当前状态：{json_data['currently']}\n\n"
        return markdown_content

    def extract_action(json_data):
        markdown_content = ""
        agents = json_data["agents"]
        for agent_name, agent_data in agents.items():
            if agent_name not in last_state.keys():
                last_state[agent_name] = {"currently": "", "location": "", "action": ""}

            location = "，".join(agent_data["action"]["event"]["address"])
            action = agent_data["action"]["event"]["describe"]

            if location == last_state[agent_name]["location"] and action == last_state[agent_name]["action"]:
                continue

            last_state[agent_name]["location"] = location
            last_state[agent_name]["action"] = action

            if len(markdown_content) < 1:
                markdown_content = f"# {json_data['time']}\n\n"
                markdown_content += "## 活动记录：\n\n"

            markdown_content += f"### {agent_name}\n"

            if len(action) < 1:
                action = "睡觉"

            markdown_content += f"位置：{location}  \n"
            markdown_content += f"活动：{action}  \n"

            markdown_content += f"\n"

        if json_data['time'] not in conversation.keys():
            return markdown_content

        markdown_content += "## 对话记录：\n\n"
        for chats in conversation[json_data['time']]:
            for agents, chat in chats.items():
                markdown_content += f"### {agents}\n\n"
                for item in chat:
                    markdown_content += f"`{item[0]}`\n> {item[1]}\n\n"
        return markdown_content

    all_markdown_content = extract_description()
    files = sorted(os.listdir(checkpoints_folder))
    for file_name in files:
        if (not file_name.endswith(".json")) or (file_name == conversation_file):
            continue

        file_path = os.path.join(checkpoints_folder, file_name)
        with open(file_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)
            content = extract_action(json_data)
            all_markdown_content += content + "\n\n"
    with open(f"{compressed_folder}/{compressed_file}", "w", encoding="utf-8") as compressed_file:
        compressed_file.write(all_markdown_content)


parser = argparse.ArgumentParser()
parser.add_argument("--name", type=str, default="", help="the name of the simulation")
args = parser.parse_args()


if __name__ == "__main__":
    name = args.name
    if len(name) < 1:
        name = input("Please enter a simulation name: ")

    while not os.path.exists(f"results/checkpoints/{name}"):
        name = input(f"'{name}' doesn't exists, please re-enter the simulation name: ")

    checkpoints_folder = f"results/checkpoints/{name}"
    compressed_folder = f"results/compressed/{name}"
    os.makedirs(compressed_folder, exist_ok=True)

    generate_report(checkpoints_folder, compressed_folder, file_markdown)
    generate_movement(checkpoints_folder, compressed_folder, file_movement)
