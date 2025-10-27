FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies needed for SPICE and KiCad
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    build-essential \
    libx11-6 \
    libxext6 \
    libxrender1 \
    libxtst6 \
    libxi6 \
    libxrandr2 \
    libxss1 \
    libgconf-2-4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libasound2 \
    libgtk-3-0 \
    libgdk-pixbuf2.0-0 \
    libcairo2 \
    libpango-1.0-0 \
    libatk1.0-0 \
    libcairo-gobject2 \
    libpangoft2-1.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# Install ngspice
RUN wget -O ngspice.tar.gz https://sourceforge.net/projects/ngspice/files/ng-spice-rework/42/ngspice-42.tar.gz/download \
    && tar -xzf ngspice.tar.gz \
    && cd ngspice-42 \
    && ./configure --with-x --enable-xspice --enable-cider --enable-openmp \
    && make -j$(nproc) \
    && make install \
    && cd .. \
    && rm -rf ngspice-42 ngspice.tar.gz

# Install KiCad (using snap for easier installation)
RUN apt-get update && apt-get install -y snapd \
    && snap install kicad --classic \
    && ln -s /snap/bin/kicad-cli /usr/bin/kicad-cli

# Set environment variables for the tools
ENV NGSPICE=/usr/local/bin/ngspice \
    KICAD_CLI=/usr/bin/kicad-cli

WORKDIR /app

# Install Python dependencies
COPY apps/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

EXPOSE 8000
CMD ["uvicorn", "apps.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]