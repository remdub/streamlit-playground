import streamlit as st
from github import Github, InputGitTreeElement
import gitlab
import yaml
import uuid
import requests
from requests.auth import HTTPBasicAuth

st.set_page_config(page_title="GitOps Portal", page_icon="☸️", layout="wide")

try:
    PROVIDER = st.secrets["provider"]
    HARBOR = st.secrets["harbor"]
except FileNotFoundError:
    st.error("❌ `.streamlit/secrets.toml` not found!")
    st.stop()
except KeyError as e:
    st.error(f"❌ Missing key in secrets: {e}")
    st.stop()

@st.cache_data(ttl=300)
def fetch_harbor_repos(base_url, project, username, password):
    api_url = f"{base_url}/api/v2.0/projects/{project}/repositories"
    auth = HTTPBasicAuth(username, password)

    try:
        resp = requests.get(api_url, auth=auth, params={"page_size": 100})
        resp.raise_for_status()
        return [r['name'].split('/')[-1] for r in resp.json()]
    except Exception as e:
        # We prefer returning None or empty list rather than crashing the UI
        return []

@st.cache_data(ttl=300)
def fetch_harbor_tags(base_url, project, repo_name, username, password):
    api_url = f"{base_url}/api/v2.0/projects/{project}/repositories/{repo_name}/artifacts"
    auth = HTTPBasicAuth(username, password)

    try:
        resp = requests.get(api_url, auth=auth, params={"page_size": 50})
        resp.raise_for_status()
        tags = []
        for artifact in resp.json():
            if 'tags' in artifact and artifact['tags']:
                for tag in artifact['tags']:
                    tags.append(tag['name'])
        return sorted(tags, reverse=True)
    except Exception:
        return ["latest"]

class HarborClient:
    def __init__(self, url, project, username, password):
        self.url = url.rstrip('/')
        self.project = project
        self.username = username
        self.password = password

    def get_repositories(self):
        return fetch_harbor_repos(self.url, self.project, self.username, self.password)

    def get_tags(self, repo_name):
        return fetch_harbor_tags(self.url, self.project, repo_name, self.username, self.password)

harbor_client = HarborClient(
    HARBOR["url"], HARBOR["project"], HARBOR["username"], HARBOR["password"]
)

def generate_files(app_name, image_full, replicas, host):
    labels = {"app.kubernetes.io/name": app_name, "app.kubernetes.io/instance": app_name}

    deployment = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": app_name, "labels": labels},
        "spec": {
            "replicas": replicas,
            "selector": {"matchLabels": labels},
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "containers": [{
                        "name": app_name,
                        "image": image_full, # Use the full image path
                        "ports": [{"name": "http", "containerPort": 8501}],
                        "readinessProbe": {"httpGet": {"path": "/", "port": 8501}}
                    }]
                }
            }
        }
    }

    service = {"apiVersion": "v1", "kind": "Service", "metadata": {"name": app_name}, "spec": {"ports": [{"port": 8501}]}}
    ingress = {"apiVersion": "networking.k8s.io/v1", "kind": "Ingress", "metadata": {"name": app_name}, "spec": {"rules": [{"host": host}]}}
    kustomization = {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "metadata": {"name": f"{app_name}-kustomization"},
        "namespace": app_name,
        "resources": ["deployments.yaml", "services.yaml", "ingress.yaml"]
    }

    return {
        "deployments.yaml": yaml.dump(deployment, sort_keys=False),
        "services.yaml": yaml.dump(service, sort_keys=False),
        "ingress.yaml": yaml.dump(ingress, sort_keys=False),
        "kustomization.yaml": yaml.dump(kustomization, sort_keys=False)
    }

def create_pr_github_atomic(token, repo_name, base_branch, app_name, file_dict, pr_title, pr_body):
    g = Github(token)
    repo = g.get_repo(repo_name)
    base_sha = repo.get_branch(base_branch).commit.sha

    # 1. Create unique branch
    new_branch = f"deploy/{app_name}-{uuid.uuid4().hex[:6]}"
    repo.create_git_ref(ref=f"refs/heads/{new_branch}", sha=base_sha)

    # 2. Prepare files for Atomic Commit
    elements = []
    for filename, content in file_dict.items():
        path = f"apps/{app_name}/{filename}"
        blob = repo.create_git_blob(content, "utf-8")
        elements.append(InputGitTreeElement(path=path, mode="100644", type="blob", sha=blob.sha))

    # 3. Create Commit
    base_tree = repo.get_git_tree(base_sha)
    tree = repo.create_git_tree(elements, base_tree)
    parent = repo.get_git_commit(base_sha)
    commit = repo.create_git_commit(f"feat: add {app_name} manifests", tree, [parent])

    # 4. Update Branch
    ref = repo.get_git_ref(f"heads/{new_branch}")
    ref.edit(commit.sha)

    # 5. Create PR with Custom Message
    pr = repo.create_pull(
        title=pr_title,
        body=pr_body,
        head=new_branch,
        base=base_branch
    )
    return pr.html_url


def create_mr_gitlab_atomic(url, token, project_id, base_branch, app_name, file_dict, pr_title, pr_body):
    gl = gitlab.Gitlab(url=url, private_token=token)
    gl.auth()
    project = gl.projects.get(project_id)

    # 1. Create unique branch
    new_branch = f"deploy/{app_name}-{uuid.uuid4().hex[:6]}"
    project.branches.create({'branch': new_branch, 'ref': base_branch})

    # 2. Prepare Actions
    actions = []
    for filename, content in file_dict.items():
        actions.append({
            'action': 'create',
            'file_path': f"apps/{app_name}/{filename}",
            'content': content
        })

    # 3. Commit
    project.commits.create({
        'branch': new_branch,
        'commit_message': f"feat: add {app_name} manifests",
        'actions': actions
    })

    # 4. Create MR with Custom Message
    mr = project.mergerequests.create({
        'source_branch': new_branch,
        'target_branch': base_branch,
        'title': pr_title,
        'description': pr_body  # GitLab uses 'description', not 'body'
    })
    return mr.web_url


# --- Main UI ---
st.title("⚓ GitOps Portal")

col1, col2 = st.columns(2)
with col1:
    st.subheader("1. Select Image (Harbor)")

    # 1. Fetch Repositories
    with st.spinner("Fetching repositories from Harbor..."):
        repo_list = harbor_client.get_repositories()

    if not repo_list:
        st.warning("No repositories found or Harbor is unreachable.")
        selected_repo = st.text_input("Manual Repo Name")
    else:
        selected_repo = st.selectbox("Repository", repo_list)

    # 2. Fetch Tags (Dependent on Repo Selection)
    if selected_repo:
        with st.spinner(f"Fetching tags for {selected_repo}..."):
            tag_list = harbor_client.get_tags(selected_repo)
            selected_tag = st.selectbox("Tag", tag_list)
    else:
        selected_tag = "latest"

    # Construct full image string
    # Format: harbor.domain.com/project/repo:tag
    full_image_string = f"{HARBOR['url'].split('//')[1]}/{HARBOR['project']}/{selected_repo}:{selected_tag}"
    st.info(f"Selected: `{full_image_string}`")

    st.subheader("2. Deployment Config")
    app_name = st.text_input("App Name", value=selected_repo if selected_repo else "my-app")
    image = st.text_input("Image", f"{full_image_string}")
    replicas = st.number_input("Replicas", 1, 5, 1)
    host = st.text_input("Host", f"{app_name}")

with col2:
    st.subheader("3. Review & Push")

    # Generate files using the Harbor image
    files = generate_files(app_name, full_image_string, replicas, host)

    tab1, tab2, tab3, tab4 = st.tabs(files.keys())
    with tab1: st.code(files["deployments.yaml"], language="yaml")
    with tab2: st.code(files["services.yaml"], language="yaml")
    with tab3: st.code(files["ingress.yaml"], language="yaml")
    with tab4: st.code(files["kustomization.yaml"], language="yaml")

    st.markdown("---")

    with st.expander("📝 Customize Pull Request Message", expanded=False):
        default_title = f"Deploy: {app_name}"
        default_body = (
            f"### New Deployment: {app_name}\n\n"
            f"- **Image:** `{image}`\n"
            f"- **Replicas:** `{replicas}`\n"
            f"- **Host:** `{host}`\n\n"
            "Generated automatically by the GitOps Portal."
        )

        pr_title = st.text_input("PR Title", value=default_title)
        pr_body = st.text_area("PR Description", value=default_body, height=150)

    if st.button("🚀 Create Pull Request", type="primary"):
        try:
            with st.spinner(f"Creating {PROVIDER} Request..."):
                if PROVIDER == "GitHub":
                    link = create_pr_github_atomic(
                        st.secrets["github"]["token"],
                        st.secrets["github"]["repo"],
                        st.secrets["github"]["base_branch"],
                        app_name,
                        files,
                        pr_title,  # Pass custom title
                        pr_body    # Pass custom body
                    )
                else:
                    link = create_mr_gitlab_atomic(
                        st.secrets["gitlab"]["url"],
                        st.secrets["gitlab"]["token"],
                        st.secrets["gitlab"]["project_id"],
                        st.secrets["gitlab"]["base_branch"],
                        app_name,
                        files,
                        pr_title,  # Pass custom title
                        pr_body    # Pass custom body
                    )

            st.success("Success! Manifests pushed.")
            st.markdown(f"👉 **[Click here to view Request]({link})**")

        except Exception as e:
            st.error(f"Error: {e}")