"""Sphinx configuration shared by local and GitHub Pages builds."""
from basinforge import __version__

project = "BasinForge"
author = "BasinForge contributors"
copyright = "2026, BasinForge contributors and credited upstream authors"
release = __version__
extensions = ["myst_parser", "sphinx.ext.autodoc", "sphinx.ext.napoleon", "sphinx.ext.mathjax"]
source_suffix = {".md": "markdown"}
root_doc = "index"
exclude_patterns = [".doctrees", "_build"]
myst_enable_extensions = ["colon_fence", "dollarmath"]
myst_heading_anchors = 4
autodoc_typehints = "description"
autodoc_member_order = "bysource"
html_theme = "sphinx_rtd_theme"
html_theme_options = {"navigation_depth": 4, "collapse_navigation": True, "sticky_navigation": True, "style_nav_header_background": "#2980b9"}
html_title = f"BasinForge {release} documentation"
html_static_path = ["_static"]
html_css_files = ["study.css"]
html_baseurl = "https://barbhuiya12.github.io/basinforge-hydro/"
html_show_sourcelink = False
html_last_updated_fmt = None
