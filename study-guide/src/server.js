'use strict';
const { loadConfig } = require('./config');
const { createApp } = require('./app');

const config = loadConfig();
const { app } = createApp(config);
app.listen(config.port, () => {
  console.log(`Study Guide running at ${config.appUrl} (port ${config.port})`);
});
