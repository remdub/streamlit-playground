import streamlit as st

st.set_page_config(layout="wide")


home_page = st.Page(
    "apps/home.py",
    title="Accueil",
    icon=":material/home:",
)

gitops_page = st.Page(
    "apps/gitops.py",
    title="GitOps",
    icon=":material/merge:",
)

pg = st.navigation([home_page, gitops_page])

pg.run()
