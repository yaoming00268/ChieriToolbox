import os
def get_all_files(paths_list):
    files = []
    for path in paths_list:
        if os.path.isfile(path) and path not in files:
            files.append(path)
        elif os.path.isdir(path):
            for f in os.listdir(path):
                fp = os.path.join(path, f)
                if os.path.isfile(fp) and fp not in files:
                    files.append(fp)
    return files
def get_rename_names_preview(paths_list, new_base_name):
    if not paths_list:
        return []
    files = get_all_files(paths_list)
    preview_list = []
    for index, old_path in enumerate(files, start=1):
        folder_path, file_name = os.path.split(old_path)
        ext = os.path.splitext(file_name)[1]
        new_name = f"{new_base_name}_{index}{ext}"
        new_path = os.path.join(folder_path, new_name)
        preview_list.append((old_path, new_path, file_name, new_name))
    return preview_list
def get_rename_extensions_preview(paths_list, old_ext, new_ext):
    if not paths_list:
        return []
    rename_all = (not old_ext) or (old_ext == '*')
    if not rename_all and not old_ext.startswith('.'):
        old_ext = '.' + old_ext
    if new_ext and not new_ext.startswith('.'):
        new_ext = '.' + new_ext
    files = get_all_files(paths_list)
    preview_list = []
    for old_path in files:
        folder_path, file_name = os.path.split(old_path)
        if rename_all or file_name.endswith(old_ext):
            base_name = os.path.splitext(file_name)[0]
            new_name = f"{base_name}{new_ext}"
            new_path = os.path.join(folder_path, new_name)
            if old_path != new_path:
                preview_list.append((old_path, new_path, file_name, new_name))
    return preview_list
def execute_rename(rename_list):
    success_count = 0
    for old_path, new_path, _, _ in rename_list:
        try:
            os.rename(old_path, new_path)
            success_count += 1
        except OSError:
            pass
    return success_count