"""
Sphinx 配置文件

用于构建 FishAsyncTask 项目的文档。
"""

import os
import sys

# 项目路径
sys.path.insert(0, os.path.abspath("../../"))

# -- 项目信息 -----------------------------------------------------------

project = "FishAsyncTask"
copyright = "2026, fishzjp"
author = "fishzjp"
version = "0.3.0"
release = "0.3.0"

# -- 扩展配置 -----------------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.todo",
    "sphinx.ext.coverage",
    "sphinx.ext.mathjax",
    "sphinx.ext.ifconfig",
    "sphinx.ext.doctest",
]

# Napoleon 配置（支持 Google 和 NumPy 风格的文档字符串）
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = False
napoleon_type_aliases = None
napoleon_attr_annotations = True

# Autodoc 配置
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
}

# Autosummary 配置
autosummary_generate = True
autosummary_generate_overwrite = True
autosummary_imported_members = True

# Intersphinx 配置（交叉引用其他项目文档）
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# Todo 扩展
todo_include_todos = True

# -- HTML 主题配置 ------------------------------------------------------

html_theme = "furo"
html_title = f"FishAsyncTask {version} 文档"
html_logo = "../../logo.png"
html_favicon = "../../logo.png"

# 主题选项
html_theme_options = {
    "sidebar_hide_name": False,
    "navigation_with_keys": True,
    "top_of_page_button": "edit",
    "source_repository": "https://github.com/fishzjp/FishAsyncTask",
    "source_branch": "main",
    "source_directory": "docs/sphinx/source/",
}

# 模板路径
templates_path = ["../_templates"]

# 静态文件路径
html_static_path = ["../_static"]

# CSS 文件
html_css_files = []

# JavaScript 文件
html_js_files = []

# -- 其他配置 -----------------------------------------------------------

# 语言
language = "zh_CN"

# 源文件编码
source_encoding = "utf-8-sig"

# 主文档
master_doc = "index"

# 忽略的文件/目录
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Pygments 高亮样式
pygments_style = "monokai"

# -- 自动文档指令 -------------------------------------------------------

# 自动生成的模块文档
autodoc_default_flags = ["members", "undoc-members", "show-inheritance"]

# 类型提示支持
autodoc_typehints = "description"
autodoc_typehints_format = "short"
