import streamlit as st

# Voir la liste des valeurs "icon" possibles ici : https://fonts.google.com/icons?icon.set=Material+Icons

st.set_page_config(layout="wide")


home_page = st.Page(
    "apps/home.py",
    title="Accueil",
    icon=":material/home:",
)

pg = st.navigation([home_page])

pg.run()
