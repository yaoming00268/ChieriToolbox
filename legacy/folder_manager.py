import os
import shutil
def flatten_and_remove_parent(paths_list):
    if not paths_list:
        return False
    success = True
    for target_folder in paths_list:
        if not os.path.exists(target_folder) or not os.path.isdir(target_folder):
            continue
        parent_dir = os.path.dirname(target_folder)
        for item in os.listdir(target_folder):
            item_path = os.path.join(target_folder, item)
            target_path = os.path.join(parent_dir, item)
            if os.path.exists(target_path):
                base, ext = os.path.splitext(item)
                counter = 1
                while os.path.exists(target_path):
                    target_path = os.path.join(parent_dir, f"{base}_{counter}{ext}")
                    counter += 1
            try:
                shutil.move(item_path, target_path)
            except Exception:
                success = False
        try:
            if not os.listdir(target_folder):
                os.rmdir(target_folder)
            else:
                shutil.rmtree(target_folder)
        except OSError:
            success = False
    return success