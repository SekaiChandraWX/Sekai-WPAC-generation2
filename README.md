# GMS 5 / GOES 9 Satellite Data Viewer

A Streamlit web application for viewing historical Geostationary Meteorological Satellite data from the second generation Western Pacific satellites covering 1995-2005.

## Features

- **Historical Coverage**: Access GMS5 and GOES9 satellite data from June 1995 to June 2005
- **Interactive Interface**: Simple date and time selection with automatic satellite detection
- **High-Quality Visualization**: Custom colormap optimized for infrared temperature data
- **Download Capability**: Save generated images as high-resolution JPEGs
- **Caching**: Built-in caching to reduce server load and improve performance
- **Fallback Processing**: Dual processing methods (Satpy + manual) for maximum compatibility

## Satellite Coverage

| Satellite | Coverage Period | Data Frequency |
|-----------|----------------|----------------|
| **GMS5** | June 13, 1995 06:00 - May 22, 2003 00:00 | Hourly |
| **GOES9** | May 22, 2003 01:00 - June 28, 2005 02:00 | Hourly |

*All times in UTC. Both satellites provide hourly infrared imagery data.*

## Deployment

### Deploy on Streamlit Cloud

1. **Fork this repository** to your GitHub account

2. **Deploy on Streamlit Cloud**:
   - Go to [share.streamlit.io](https://share.streamlit.io)
   - Click "New app"
   - Select your forked repository
   - Set the main file path to `app.py`
   - Click "Deploy"

### Local Development

```bash
# Clone the repository
git clone https://github.com/yourusername/gms5-goes9-satellite-viewer.git
cd gms5-goes9-satellite-viewer

# Install dependencies
pip install -r requirements.txt

# Run the application
streamlit run app.py
```

## Required Files

Make sure your repository contains these files:

- `app.py` - Main Streamlit application
- `requirements.txt` - Python dependencies
- `README.md` - This documentation

## Usage

1. **Select Date**: Choose any date within the satellite coverage period (1995-2005)
2. **Select Hour**: Pick any hour from 0-23 UTC (both satellites provide hourly data)
3. **Generate Image**: Click the "Generate Image" button
4. **Download**: Save the generated high-resolution image

## Performance Notes

- **Caching**: Data is cached for 1 hour to reduce FTP server load
- **Processing Time**: Initial requests may take 30-60 seconds due to FTP downloads
- **File Sizes**: Generated images are high-resolution and may be several MB
- **Fallback System**: If Satpy fails, the app uses manual data reading

## Technical Details

### Data Source
- **FTP Server**: gms.cr.chiba-u.ac.jp
- **Format**: Compressed tar files containing gzipped VISSR data
- **Processing**: Data is decompressed and converted to temperature values

### Visualization
- **Colormap**: Custom colormap optimized for infrared imagery
- **Vertical Stretch**: 1.35x vertical stretching applied for better visualization
- **Resolution**: Images generated at 300 DPI for high quality
- **Temperature Range**: -100°C to +40°C

### Libraries Used
- **Streamlit**: Web application framework
- **Satpy**: Satellite data processing (with manual fallback)
- **Matplotlib**: Data visualization
- **NumPy + SciPy**: Data processing and image manipulation
- **Pillow**: Image manipulation and watermarking

## Troubleshooting

### Common Issues

**"Failed to download the file"**
- The FTP server may be temporarily unavailable
- Check your internet connection
- Try a different date/time

**"Date is out of coverage period"**
- Verify the date is within 1995-2005
- Check the satellite coverage table above

**Processing Errors**
- The app includes fallback processing methods
- If Satpy fails, it automatically tries manual data reading
- Contact support if both methods fail consistently

### Performance Optimization
- Images are cached to reduce repeated FTP requests
- Temporary files are automatically cleaned up
- Processing uses optimized algorithms for cloud deployment

## License

This project is for educational and research purposes. Please respect the data source and cite appropriately when using generated images.

## Credits

- **Original Script**: Sekai Chandra (@Sekai_WX)
- **Data Source**: Chiba University GMS/GOES Archive
- **Streamlit Conversion**: [Your name here]

## Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

---

*For questions or support, please open an issue on GitHub.*