/**
 * 文件批量整理大师 (File Suite)
 * 正则批量改名、前后缀替换、数字序号对齐补零
 */

const FileSuite = (function () {
  function previewRename(fileNames, options) {
    const {
      prefix = "",
      suffix = "",
      findText = "",
      replaceText = "",
      useRegex = false,
      padZeros = 0
    } = options;

    return fileNames.map((name, index) => {
      let extIndex = name.lastIndexOf(".");
      let base = extIndex !== -1 ? name.slice(0, extIndex) : name;
      let ext = extIndex !== -1 ? name.slice(extIndex) : "";

      // Replace text / regex
      if (findText) {
        try {
          if (useRegex) {
            const re = new RegExp(findText, "g");
            base = base.replace(re, replaceText);
          } else {
            base = base.split(findText).join(replaceText);
          }
        } catch (e) {}
      }

      // Zero padding number if applicable
      if (padZeros > 0) {
        const numStr = String(index + 1).padStart(padZeros, "0");
        base = `${base}_${numStr}`;
      }

      // Add prefix & suffix
      const newName = `${prefix}${base}${suffix}${ext}`;
      return {
        original: name,
        renamed: newName
      };
    });
  }

  return {
    previewRename
  };
})();

window.FileSuite = FileSuite;
