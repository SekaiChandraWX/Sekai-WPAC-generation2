import os
import gzip
import tarfile
import ftplib
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from datetime import datetime
import streamlit as st
import tempfile
import time
import struct
from scipy import ndimage
from PIL import Image, ImageDraw, ImageFont
import warnings
import shutil

# Constants
FTP_HOST = "gms.cr.chiba-u.ac.jp"
GMS5_START_DATE = datetime(1995, 6, 13, 6)
GMS5_END_DATE = datetime(2003, 5, 22, 0)
GOES9_START_DATE = datetime(2003, 5, 22, 1)
GOES9_END_DATE = datetime(2005, 6, 28, 2)
VERTICAL_STRETCH = 1.35

def comprehensive_patch_gms5_reader():
    """Comprehensive patch for GMS5 reader to handle historical file variants"""
    try:
        from satpy.readers.gms import gms5_vissr_l1b
        
        # Check if already patched
        if hasattr(gms5_vissr_l1b.GMS5VISSRFileHandler, '_patched_comprehensive'):
            return

        # Store original methods
        original_read_image_data = gms5_vissr_l1b.GMS5VISSRFileHandler._read_image_data
        original_get_actual_shape = gms5_vissr_l1b.GMS5VISSRFileHandler._get_actual_shape

        def safe_read_from_file_obj(file_obj, dtype, count, offset=0):
            """Safe version of read_from_file_obj that handles buffer size issues"""
            file_obj.seek(offset)
            remaining_data = file_obj.read()
            actual_bytes = len(remaining_data)
            bytes_needed = dtype.itemsize * count

            if actual_bytes < bytes_needed:
                actual_count = actual_bytes // dtype.itemsize
                if actual_count == 0:
                    raise ValueError(f"Not enough data to read even one record of type {dtype}")
            else:
                actual_count = count
                remaining_data = remaining_data[:bytes_needed]

            return np.frombuffer(remaining_data, dtype=dtype, count=actual_count)

        def patched_read_image_data(self):
            """Patched version that uses safe file reading"""
            try:
                return original_read_image_data(self)
            except (ValueError, struct.error) as e:
                if "buffer is smaller than requested size" in str(e) or "unpack requires" in str(e):
                    return self._read_image_data_completely_safe()
                raise e

        def patched_get_actual_shape(self):
            """Patched version that calculates safe shape"""
            try:
                return original_get_actual_shape(self)
            except Exception:
                return self._get_file_based_shape()

        def _read_image_data_completely_safe(self):
            """Completely safe image data reading"""
            specs = self._get_image_data_type_specs()
            file_size = os.path.getsize(self._filename)
            available_data = file_size - specs["offset"]
            max_records = available_data // specs["dtype"].itemsize

            from satpy.readers.utils import generic_open
            with generic_open(self._filename, "rb") as file_obj:
                return safe_read_from_file_obj(
                    file_obj,
                    dtype=specs["dtype"],
                    count=max_records,
                    offset=specs["offset"]
                )

        def _get_file_based_shape(self):
            """Calculate shape based on actual file content"""
            try:
                _, nominal_pixels = self._get_nominal_shape()
            except:
                nominal_pixels = 2366

            specs = self._get_image_data_type_specs()
            file_size = os.path.getsize(self._filename)
            available_data = file_size - specs["offset"]

            if specs["dtype"].names:
                sample_record_size = specs["dtype"].itemsize
                max_lines = available_data // sample_record_size
            else:
                bytes_per_pixel = specs["dtype"].itemsize
                total_pixels = available_data // bytes_per_pixel
                max_lines = total_pixels // nominal_pixels

            return max_lines, nominal_pixels

        # Apply the patches
        gms5_vissr_l1b.GMS5VISSRFileHandler._read_image_data = patched_read_image_data
        gms5_vissr_l1b.GMS5VISSRFileHandler._get_actual_shape = patched_get_actual_shape
        gms5_vissr_l1b.GMS5VISSRFileHandler._read_image_data_completely_safe = _read_image_data_completely_safe
        gms5_vissr_l1b.GMS5VISSRFileHandler._get_file_based_shape = _get_file_based_shape
        gms5_vissr_l1b.GMS5VISSRFileHandler._patched_comprehensive = True
        gms5_vissr_l1b.read_from_file_obj = safe_read_from_file_obj

    except ImportError:
        st.warning("Satpy not available - will use manual reading only")

def create_colormap():
    """Create custom satellite colormap"""
    return mcolors.LinearSegmentedColormap.from_list("", [
        (0 / 140, "#000000"), (60 / 140, "#fffdfd"), (60 / 140, "#05fcfe"),
        (70 / 140, "#010071"), (80 / 140, "#00fe24"), (90 / 140, "#fbff2d"),
        (100 / 140, "#fd1917"), (110 / 140, "#000300"), (120 / 140, "#e1e4e5"),
        (120 / 140, "#eb6fc0"), (130 / 140, "#9b1f94"), (140 / 140, "#330f2f")
    ]).reversed()

def try_manual_reading(file_path, year, month, day, hour):
    """Fallback manual reading method if Satpy fails"""
    try:
        with open(file_path, 'rb') as f:
            data = f.read()

        # Try to extract dimensions from header
        if len(data) > 12:
            try:
                width = struct.unpack('>H', data[8:10])[0]
                height = struct.unpack('>H', data[10:12])[0]
                if width > 5000 or height > 5000 or width < 100 or height < 100:
                    width = 2366
                    height = 2366
            except:
                width = 2366
                height = 2366
        else:
            width = 2366
            height = 2366

        # Skip header and get image data
        header_size = 352
        if len(data) > header_size:
            image_data = data[header_size:]
            image_array = np.frombuffer(image_data, dtype=np.uint8)

            available_pixels = len(image_array)
            target_pixels = width * height
            
            if available_pixels >= target_pixels:
                image = image_array[:target_pixels].reshape(height, width)
            else:
                height = available_pixels // width
                if height < 100:
                    side = int(np.sqrt(available_pixels))
                    width = height = side
                    image = image_array[:side*side].reshape(height, width)
                else:
                    image = image_array[:height * width].reshape(height, width)

            # Convert to temperature (approximated calibration)
            temperature = 180.0 + (image.astype(np.float32) / 255.0) * (320.0 - 180.0)

            # Create xarray DataArray to mimic Satpy output
            import xarray as xr
            ir1_data = xr.DataArray(
                temperature,
                dims=['y', 'x'],
                attrs={
                    'platform': 'GMS-5',
                    'sensor': 'VISSR',
                    'units': 'K',
                    'standard_name': 'brightness_temperature',
                    'start_time': datetime(year, month, day, hour),
                }
            )
            return ir1_data
        else:
            raise ValueError("Insufficient data in file")

    except Exception as e:
        print(f"Manual reading failed: {e}")
        return None

@st.cache_data(ttl=3600)
def fetch_file(year, month, day, hour):
    """Fetch satellite file from FTP server"""
    temp_dir = tempfile.mkdtemp()
    
    try:
        request_time = datetime(year, month, day, hour)

        if request_time < GMS5_START_DATE or request_time > GOES9_END_DATE:
            return None, None, "The requested date is out of this dataset's period of coverage!"

        if GMS5_START_DATE <= request_time <= GMS5_END_DATE:
            ftp_base_path = "/pub/GMS5/VISSR"
            satellite = "GMS5"
        elif GOES9_START_DATE <= request_time <= GOES9_END_DATE:
            ftp_base_path = "/pub/GOES9-Pacific/VISSR"
            satellite = "GOES9"
        else:
            return None, None, "The requested date is out of this dataset's period of coverage!"

        ftp_dir = f"{ftp_base_path}/{year}{month:02d}/{day:02d}"
        file_name = f"VISSR_{satellite}_{year}{month:02d}{day:02d}{hour:02d}00.tar"
        local_tar_path = os.path.join(temp_dir, file_name)

        progress_bar = st.progress(0)
        status_text = st.empty()
        status_text.text("Connecting to FTP server...")

        try:
            with ftplib.FTP(FTP_HOST, timeout=30) as ftp:
                ftp.login()
                progress_bar.progress(20)
                status_text.text("Connected. Navigating to directory...")
                
                try:
                    ftp.cwd(ftp_dir)
                except ftplib.error_perm as e:
                    return None, None, f"Directory not found on FTP server: {e}"
                
                progress_bar.progress(40)
                status_text.text("Downloading file...")
                
                with open(local_tar_path, 'wb') as local_file:
                    try:
                        ftp.retrbinary(f"RETR {file_name}", local_file.write)
                    except ftplib.error_perm as e:
                        return None, None, f"File not found on FTP server: {e}"
                
                progress_bar.progress(60)
                status_text.text("File downloaded. Extracting...")

            # Verify download
            if not os.path.exists(local_tar_path) or os.path.getsize(local_tar_path) == 0:
                return None, None, "Downloaded file is empty or missing"

            progress_bar.progress(80)
            status_text.text("Extracting archive...")

            # Extract the file
            with tarfile.open(local_tar_path, 'r') as tar:
                for member in tar.getmembers():
                    if member.name.endswith("IR1.A.IMG.gz"):
                        member.name = os.path.basename(member.name)
                        tar.extract(member, path=temp_dir)
                        extracted_path = os.path.join(temp_dir, member.name)

                        # Create the filename that Satpy expects
                        satpy_filename = f"VISSR_{year}{month:02d}{day:02d}_{hour:02d}00_IR1.A.IMG"
                        local_img_path = os.path.join(temp_dir, satpy_filename)

                        with gzip.open(extracted_path, 'rb') as f_in:
                            with open(local_img_path, 'wb') as f_out:
                                f_out.write(f_in.read())

                        progress_bar.progress(100)
                        status_text.text("Processing complete!")
                        return local_img_path, satellite, None

            return None, None, "Could not find IR1.A.IMG.gz file in tar archive"

        except ftplib.all_errors as e:
            return None, None, f"FTP error: {e}"
        except tarfile.TarError as e:
            return None, None, f"Tar extraction error: {e}"
        except Exception as e:
            return None, None, f"Unexpected error: {e}"

    except Exception as e:
        return None, None, f"General error in fetch_file: {e}"

def process_and_plot(file_path, satellite, year, month, day, hour):
    """Process and plot the satellite data"""
    temp_dir = os.path.dirname(file_path)
    
    try:
        # Apply comprehensive patches
        comprehensive_patch_gms5_reader()
        warnings.filterwarnings('ignore')

        ir1_data = None

        try:
            # Try with Satpy first
            print("Attempting to read with Satpy...")
            from satpy import Scene
            scene = Scene([file_path], reader='gms5-vissr_l1b', reader_kwargs={"mask_space": False})
            scene.load(["IR1"])
            ir1_data = scene["IR1"]
            satellite_name = ir1_data.attrs.get('platform', satellite)
            print("Successfully loaded with Satpy")

        except Exception as e:
            print(f"Satpy failed: {e}")
            print("Trying manual reading method...")

            # Try manual reading as fallback
            ir1_data = try_manual_reading(file_path, year, month, day, hour)

            if ir1_data is None:
                raise ValueError("Both Satpy and manual reading failed")

            satellite_name = satellite
            print("Successfully loaded with manual method")

        # Process the data
        kelvin_values = ir1_data.values
        celsius_values = kelvin_values - 273.15

        # Apply vertical stretch
        if VERTICAL_STRETCH != 1.0:
            original_height, original_width = celsius_values.shape
            celsius_values = ndimage.zoom(celsius_values, (VERTICAL_STRETCH, 1.0), order=1)

        # Create visualization
        custom_cmap = create_colormap()
        vmin = -100
        vmax = 40

        fig, ax = plt.subplots(figsize=(12, 10), dpi=300)
        ax.imshow(celsius_values, cmap=custom_cmap, vmin=vmin, vmax=vmax)

        ax.grid(False)
        ax.axis('off')
        ax.set_xticks([])
        ax.set_yticks([])

        # Remove all borders
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
        ax.spines['left'].set_visible(False)

        # Save the plot
        plot_path = os.path.join(temp_dir, 'satellite_data_plot.jpg')
        plt.savefig(plot_path, format='jpg', dpi=300, bbox_inches='tight', pad_inches=0)
        plt.close()

        # Open the saved image and stretch it sideways by 75%
        img = Image.open(plot_path)
        width, height = img.size
        new_width = int(width * 1.75)
        img = img.resize((new_width, height), Image.LANCZOS)

        # Add watermarks
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype("arial.ttf", 50)
        except:
            font = ImageFont.load_default()
        
        watermark_text_top = f"{satellite_name} Data for {year}-{month:02d}-{day:02d} at {hour:02d}:00 UTC"
        watermark_text_bottom = "Plotted by Sekai Chandra @Sekai_WX"
        draw.text((10, 10), watermark_text_top, fill="white", font=font)
        draw.text((10, height - 70), watermark_text_bottom, fill="red", font=font)

        # Save the final image
        final_image_path = os.path.join(temp_dir, 'final_satellite_data_plot.jpg')
        img.save(final_image_path)

        return final_image_path

    except Exception as e:
        raise e
    finally:
        # Clean up files safely
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
        except:
            pass

def main():
    st.set_page_config(
        page_title="GMS 5 / GOES 9 Satellite Data Archive (1995-2005)",
        layout="centered"
    )
    
    st.title("GMS 5 / GOES 9 Satellite Data Viewer")
    
    # Input form in columns
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        year = st.number_input("Year", min_value=1995, max_value=2005, value=2000)
    with col2:
        month = st.number_input("Month", min_value=1, max_value=12, value=1)
    with col3:
        day = st.number_input("Day", min_value=1, max_value=31, value=1)
    with col4:
        # All satellites in this period are hourly
        hour = st.selectbox("Hour (UTC)", list(range(24)), index=0)
    
    # Warning message
    st.warning("WARNING: Image WILL take 30-60 seconds to generate!")
    
    # Perfectly centered generate button with red styling
    col1, col2, col3 = st.columns([2, 1, 2])
    with col2:
        st.markdown(
            """
            <style>
            .stButton > button {
                background-color: #ff4b4b;
                color: white;
                border: none;
                width: 100%;
            }
            .stButton > button:hover {
                background-color: #ff6b6b;
                border: none;
            }
            </style>
            """,
            unsafe_allow_html=True
        )
        generate_clicked = st.button("Generate Image")
    
    if generate_clicked:
        with st.spinner("Processing satellite data..."):
            start_time = time.time()
            
            final_image_path, satellite_used, error_message = fetch_file(
                year, month, day, hour
            )
            
            if error_message:
                st.error(f"Error: {error_message}")
            elif final_image_path:
                try:
                    processed_image_path = process_and_plot(
                        final_image_path, satellite_used, year, month, day, hour
                    )
                    
                    processing_time = time.time() - start_time
                    st.success(f"Image generated successfully in {processing_time:.1f} seconds using {satellite_used}!")
                    
                    # Display the image
                    st.image(processed_image_path, caption=f"{satellite_used} Satellite Data - {year}-{month:02d}-{day:02d} {hour:02d}:00 UTC")
                    
                    # Provide download button
                    with open(processed_image_path, "rb") as file:
                        st.download_button(
                            label="Download Image",
                            data=file.read(),
                            file_name=f"{satellite_used}_{year}{month:02d}{day:02d}_{hour:02d}00_UTC.jpg",
                            mime="image/jpeg"
                        )
                        
                except Exception as e:
                    st.error(f"Error processing image: {e}")
            else:
                st.error("Failed to generate image. Please try again.")

if __name__ == "__main__":
    main()