
const express = require('express');
const http = require('http');
const { Server } = require("socket.io");
const cors = require('cors');

const app = express();
app.use(cors());
app.use(express.json());

const server = http.createServer(app);
const io = new Server(server, {
  cors: {
    origin: "*", // Allow all origins for dev
    methods: ["GET", "POST"]
  }
});

// Store connected clients
let clients = [];

io.on('connection', (socket) => {
  console.log('Mobile App Connected:', socket.id);
  clients.push(socket);

  socket.on('disconnect', () => {
    console.log('Mobile App Disconnected:', socket.id);
    clients = clients.filter(c => c.id !== socket.id);
  });
});

// Endpoint for Python Edge Script to trigger alert
app.post('/api/alert', (req, res) => {
  const { camera_id, alert_type, description, image_base64 } = req.body;
  
  console.log(`[ALERT RECEIVED] ${alert_type} from ${camera_id}`);

  // Push to all connected mobile apps
  io.emit('critical_alert', {
    title: alert_type,
    desc: description,
    camera: camera_id,
    timestamp: new Date().toISOString()
  });

  res.json({ status: 'success', message: 'Alert dispatched to mobile clients' });
});

const PORT = process.env.PORT || 3001;
server.listen(PORT, () => {
  console.log(`VisionSafe Backend running on port ${PORT}`);
});
