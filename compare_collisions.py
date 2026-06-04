import json
import os

def analyze():
    # 路径定义
    base_dir = os.path.dirname(__file__)
    csv_path = os.path.join(base_dir, "static", "assets", "the_ville", "matrix", "maze", "collision_maze.csv")
    json_path = os.path.join(base_dir, "static", "assets", "the_ville", "visuals", "the_ville_jan7.json")
    
    if not os.path.exists(csv_path):
        print(f"Error: CSV path not found: {csv_path}")
        return
    if not os.path.exists(json_path):
        print(f"Error: JSON path not found: {json_path}")
        return

    # 1. 读取 CSV 碰撞迷宫（140x100，单行用逗号分隔，0 表示空地，非0表示阻挡）
    with open(csv_path, "r") as f:
        csv_raw = f.read().strip()
    csv_values = [int(v.strip()) for v in csv_raw.split(",") if v.strip()]
    
    print(f"CSV values count: {len(csv_values)}")
    
    # 2. 读取 Tiled JSON 中的 Collisions 图层
    with open(json_path, "r", encoding="utf-8") as f:
        tiled_data = json.load(f)
        
    width = tiled_data["width"]
    height = tiled_data["height"]
    print(f"Tiled Map Size: {width}x{height} (expected 140x100)")
    
    collisions_layer = None
    for layer in tiled_data["layers"]:
        if layer["name"] == "Collisions":
            collisions_layer = layer
            break
            
    if not collisions_layer:
        print("Error: 'Collisions' layer not found in JSON map!")
        return
        
    json_data = collisions_layer["data"]
    print(f"JSON collisions layer data count: {len(json_data)}")
    
    # 3. 对比两者的障碍物差异
    # 注意：Tiled JSON 也是从左到右、从上到下按 140x100 铺平的。
    # 0 代表无碰撞瓦片，非0代表碰撞墙体
    diff_count = 0
    mismatch_list = []
    
    for y in range(height):
        for x in range(width):
            idx = y * width + x
            csv_val = csv_values[idx]
            json_val = json_data[idx]
            
            # 判断阻挡状态：CSV 里的非0值是墙，JSON 里的非0值也是墙
            csv_is_wall = (csv_val != 0)
            json_is_wall = (json_val != 0)
            
            if csv_is_wall != json_is_wall:
                diff_count += 1
                if diff_count <= 20: # 仅记录前20个差异点
                    mismatch_list.append((x, y, csv_val, json_val))
                    
    print(f"\nTotal collisions mismatch grid count: {diff_count} / {width*height}")
    
    if diff_count > 0:
        print("Here are some of the mismatching tiles (x, y) [CSV Value vs JSON Value]:")
        for x, y, cv, jv in mismatch_list:
            c_type = "Wall" if cv != 0 else "Free"
            j_type = "Wall" if jv != 0 else "Free"
            print(f"  ({x:3d}, {y:3d}): CSV={c_type} ({cv}), JSON={j_type} ({jv})")
    else:
        print("Perfect Match! The collision database perfectly matches the Tiled visual layers!")

if __name__ == "__main__":
    analyze()
