const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function configureProxy(app) {
  app.use('/game-api', createProxyMiddleware({
    target: 'http://127.0.0.1:9436',
    changeOrigin: true,
    pathRewrite: { '^/game-api': '' }
  }));
};
