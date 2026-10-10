import streamlit as st

st.set_page_config(page_title="Health Edu Assistant", page_icon="🩺", layout="wide")

st.title("🩺 Health & Medical Information Assistant")
st.write("Welcome! Medical concepts and lab terms in simple language.")

user_query = st.text_input("Enter a medical term or lab test name (e.g., Hemoglobin, ECG):")

if st.button("Explain"):
    if user_query:
        st.success(f"Showing results for: **{user_query}**")
        st.info("App is successfully connected and running!")
    else:
        st.warning("Please enter a medical term.")
        
