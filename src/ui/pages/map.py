import streamlit as st
import os
from src.core.persistence import ProjectMemory

def render_map_page(memory: ProjectMemory):
    st.header("World Map")
    st.caption("Upload and view the map of your universe.")

    # Image Upload
    uploaded_file = st.file_uploader("Upload Map Image", type=["png", "jpg", "jpeg"])
    
    if uploaded_file is not None:
        # Create an uploads directory if it doesn't exist
        os.makedirs("data/uploads", exist_ok=True)
        file_path = os.path.join("data/uploads", uploaded_file.name)
        
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        memory.update_map(file_path)
        st.success("Map uploaded successfully!")
        
    # Display Map
    current_map = memory.data.get("map_settings", {}).get("image_path", "")
    if current_map and os.path.exists(current_map):
        st.image(current_map, caption="World Map", use_container_width=True)
        if st.button("Clear Map"):
            memory.update_map("")
            st.rerun()
    elif not current_map:
        st.info("No map image uploaded yet.")
    else:
        st.warning(f"Map image not found at path: {current_map}")
