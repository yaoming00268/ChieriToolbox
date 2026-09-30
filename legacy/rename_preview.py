import os
from getfiles import get_all_files
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