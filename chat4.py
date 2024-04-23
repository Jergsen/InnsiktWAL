import streamlit as st
import uuid
import time
import pandas as pd
import io
from openai import OpenAI
from typing_extensions import override
from openai import AssistantEventHandler


# Initialize OpenAI client
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

assistant_id = st.secrets["OPENAI_ASSISTANT_ID2"]

# Initialize session state variables
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "run" not in st.session_state:
    st.session_state.run = {"status": None}

if "messages" not in st.session_state:
    st.session_state.messages = []

if "retry_error" not in st.session_state:
    st.session_state.retry_error = 0

# Set up the page
st.set_page_config(
    page_title="Coop innsikt assistent",
    page_icon="Bilder/standard_coop-logo.png",
    layout="wide",
    initial_sidebar_state="auto",
)

# File uploader for CSV, XLS, XLSX
uploaded_file = st.file_uploader("Last opp fil", type=["csv", "xls", "xlsx"])

if uploaded_file is not None:
    # Determine the file type
    file_type = uploaded_file.type

    try:
        # Read the file into a Pandas DataFrame
        if file_type == "text/csv":
            df = pd.read_csv(uploaded_file)
        elif file_type in ["application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]:
            df = pd.read_excel(uploaded_file)

        # Convert DataFrame to JSON
        json_str = df.to_json(orient='records', indent=4)
        file_stream = io.BytesIO(json_str.encode())

        # Upload JSON data to OpenAI and store the file ID
        file_response = client.files.create(file=file_stream, purpose='answers')
        st.session_state.file_id = file_response.id
        st.success("File uploaded successfully to OpenAI!")

        # Optional: Display and Download JSON
        st.text_area("JSON Output", json_str, height=300)
        st.download_button(label="Download JSON", data=json_str, file_name="converted.json", mime="application/json")
    
    except Exception as e:
        st.error(f"An error occurred: {e}")

# Initialize OpenAI assistant
if "assistant" not in st.session_state:
    st.session_state.assistant = client.beta.assistants.retrieve(assistant_id)
    st.session_state.thread = client.beta.threads.create(
        metadata={'session_id': st.session_state.session_id}
    )


if hasattr(st.session_state.run, 'status') and st.session_state.run.status == "completed":
    # Retrieve messages from the thread
    st.session_state.messages = client.beta.threads.messages.list(
        thread_id=st.session_state.thread.id
    )

    for message in reversed(st.session_state.messages.data):
          # Print original message  
        print("Original message:")
        for content in message.content:
            print(content.text.value)

        if message.role in ["user", "assistant"]:

            message_text = ""
            citations = []
        
            for content in message.content:
                if content.type == "text":
                    message_text += content.text.value
                    for annotation in content.text.annotations:
                        if annotation.type == "file_citation":
                            file_id = annotation.file_citation.file_id
                            file = client.files.retrieve(file_id)
                            citation = f"[{len(citations)+1}] {file.filename}"
                            citations.append(citation)
                            message_text = message_text.replace(annotation.text, citation)

            message_text += "\n\n" + "\n".join(citations)

            print("Message with annotations:")
            print(message_text)
        
            with st.chat_message(message.role):
                st.markdown(message_text)


# Chat input and message creation with file ID
if prompt := st.chat_input("Hva lurer du på?"):
    with st.chat_message('user'):
        st.write(prompt)

    message_data = {
        "thread_id": st.session_state.thread.id,
        "role": "user",
        "content": prompt
    }

    # Include file ID in the request if available
    if "file_id" in st.session_state:
        message_data["file_ids"] = [st.session_state.file_id]

    st.session_state.messages = client.beta.threads.messages.create(**message_data)

    st.session_state.run = client.beta.threads.runs.create(
        thread_id=st.session_state.thread.id,
        assistant_id=st.session_state.assistant.id,
    )
    if st.session_state.retry_error < 3:
        time.sleep(1)
        st.rerun()



# Handle run status
if hasattr(st.session_state.run, 'status'):
    if st.session_state.run.status == "running":
        with st.chat_message('assistant'):
            st.write("Thinking ......")
        if st.session_state.retry_error < 3:
            time.sleep(1)
            st.rerun()

    elif st.session_state.run.status == "failed":
        st.session_state.retry_error += 1
        with st.chat_message('assistant'):
            if st.session_state.retry_error < 3:
                st.write("Run failed, retrying ......")
                time.sleep(3)
                st.rerun()
            else:
                st.error("FAILED: The OpenAI API is currently processing too many requests. Please try again later ......")

    elif st.session_state.run.status != "completed":
        st.session_state.run = client.beta.threads.runs.retrieve(
            thread_id=st.session_state.thread.id,
            run_id=st.session_state.run.id,
        )
        if st.session_state.retry_error < 3:
            time.sleep(3)
            st.rerun()


class EventHandler(AssistantEventHandler):
    @override
    def on_text_created(self, text) -> None:
        print(f"\nassistant > ", end="", flush=True)

    @override
    def on_text_delta(self, delta, snapshot):
        print(delta.value, end="", flush=True)

    def on_tool_call_created(self, tool_call):
        print(f"\nassistant > {tool_call.type}\n", flush=True)

    def on_tool_call_delta(self, delta, snapshot):
        if delta.type == 'code_interpreter':
            if delta.code_interpreter.input:
                print(delta.code_interpreter.input, end="", flush=True)
            if delta.code_interpreter.outputs:
                print(f"\n\noutput >", flush=True)
                for output in delta.code_interpreter.outputs:
                    if output.type == "logs":
                        print(f"\n{output.logs}", flush=True)