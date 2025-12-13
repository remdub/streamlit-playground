from streamlit.testing.v1 import AppTest


def test_home_title():
    at = AppTest.from_file("../main.py").run()
    assert at.title[0].value == "Streamlit Playground"
