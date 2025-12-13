import streamlit as st

st.title("Streamlit Playground")
st.write("Utilisez la navigation pour accéder aux différents POCs.")

st.header("Pour tester localement")
st.code(
    """
git clone https://github.com/remdub/streamlit-playground.git
cd streamlit-playground
make start""",
    language="bash",
)