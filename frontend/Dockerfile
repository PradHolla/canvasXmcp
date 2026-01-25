# Stage 1: Build the React App
# CHANGE 18 TO 22 HERE:
FROM node:22-alpine as build

WORKDIR /app
COPY package*.json ./
RUN npm install

# Copy source code
COPY . .

# Accept the API URL as a build argument and set as env var for Vite
ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}

# Debug: Print the env var to verify it's set
RUN echo "Building with VITE_API_URL: $VITE_API_URL"

# Build the static files
RUN npm run build

# Stage 2: Serve with Nginx
FROM nginx:alpine

# 1. Install utils for debugging (optional but helpful)
# RUN apk add --no-cache bash

# 2. Copy the build artifacts
COPY --from=build /app/dist /usr/share/nginx/html

# 3. Copy Nginx Config
# We delete the default config first to be absolutely sure
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 4. EXPLICITLY copy mime.types (fixes "text/plain" errors)
# (Nginx usually has this, but let's be safe)
# COPY --from=build /app/package.json /tmp/dummy 

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]