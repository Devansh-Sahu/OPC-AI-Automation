import os
from pathlib import Path

BASE_DIR = Path(r"C:\Users\devansh\OneDrive\Desktop\Open Source Engineer\frontend")

app_pages = [
    "discover/page.tsx",
    "repositories/page.tsx",
    "issues/page.tsx",
    "agent-runs/page.tsx",
    "pull-requests/page.tsx",
    "innovation/page.tsx",
    "analytics/page.tsx",
    "settings/page.tsx"
]

page_template = """export default function Page() {
  return (
    <div className="p-8">
      <h1 className="text-3xl font-bold mb-4 capitalize">{PAGE_NAME}</h1>
      <p className="text-gray-400">This page is under construction.</p>
    </div>
  )
}
"""

components = [
    "layout/sidebar.tsx",
    "layout/header.tsx",
    "layout/page-header.tsx",
    "dashboard/kpi-card.tsx",
    "dashboard/activity-feed.tsx",
    "dashboard/quick-actions.tsx",
    "agent-run-live.tsx",
    "pr-review-card.tsx",
    "issue-complexity-badge.tsx",
    "repo-discovery-card.tsx",
    "contribution-streak.tsx"
]

component_template = """export function Component() {
  return <div>Component</div>
}
"""

lib_files = [
    "api.ts",
    "websocket.ts",
    "utils.ts"
]

lib_template = """// Lib file
export const utils = {}
"""

def write_file(path, content):
    full_path = BASE_DIR / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content)

for page in app_pages:
    page_name = page.split('/')[0]
    write_file(f"app/{page}", page_template.replace("{PAGE_NAME}", page_name.replace('-', ' ')))

for comp in components:
    write_file(f"components/{comp}", component_template)

for lib in lib_files:
    write_file(f"lib/{lib}", lib_template)
