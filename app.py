#!/usr/bin/env python3
"""
Professional Trading Dashboard - Flask Backend
Integrates with Binance API and provides real-time WebSocket updates
Reads API keys from .env file for security
"""

import os
import json
import asyncio
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

try:
    from binance import Client, ThreadedWebsocketManager
except ImportError as e:
    print("ImportError:", e)
    raise   # let the real error show


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(f'trading_dashboard_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Flask app setup
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

class TradingDashboardBackend:
    """Backend service for professional trading dashboard"""
    
    def __init__(self):
        self.api_key = os.getenv('BINANCE_API_KEY')
        self.api_secret = os.getenv('BINANCE_API_SECRET')
        self.testnet = os.getenv('BINANCE_TESTNET', 'true').lower() == 'true'
        
        if not self.api_key or not self.api_secret:
            logger.error("BINANCE_API_KEY and BINANCE_API_SECRET must be set in .env file")
            raise ValueError("Missing API credentials in .env file")
        
        # Initialize Binance client
        try:
            self.client = Client(
                self.api_key,
                self.api_secret,
                testnet=self.testnet
            )
            
            # Test connection
            self.client.futures_ping()
            logger.info("✅ Connected to Binance Futures API")
            
        except Exception as e:
            logger.error(f"Failed to connect to Binance: {e}")
            raise
        
        # WebSocket manager for real-time data
        self.twm = None
        self.active_streams = set()
        self.current_symbol = 'BTCUSDT'
        
    def start_websocket_manager(self):
        """Start WebSocket manager for real-time data"""
        try:
            self.twm = ThreadedWebSocketManager(
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.testnet
            )
            self.twm.start()
            logger.info("✅ WebSocket manager started")
            
            # Start default streams
            self.subscribe_to_symbol(self.current_symbol)
            
        except Exception as e:
            logger.error(f"Failed to start WebSocket manager: {e}")
    
    def subscribe_to_symbol(self, symbol):
        """Subscribe to real-time data for a symbol"""
        try:
            # Stop existing streams
            self.stop_all_streams()
            
            self.current_symbol = symbol.upper()
            
            # Price ticker stream
            ticker_stream = self.twm.start_symbol_ticker_socket(
                callback=self.handle_ticker_update,
                symbol=self.current_symbol
            )
            self.active_streams.add(ticker_stream)
            
            # Order book stream
            depth_stream = self.twm.start_depth_socket(
                callback=self.handle_depth_update,
                symbol=self.current_symbol
            )
            self.active_streams.add(depth_stream)
            
            # Recent trades stream
            trades_stream = self.twm.start_trade_socket(
                callback=self.handle_trade_update,
                symbol=self.current_symbol
            )
            self.active_streams.add(trades_stream)
            
            logger.info(f"✅ Subscribed to {self.current_symbol} streams")
            
        except Exception as e:
            logger.error(f"Failed to subscribe to {symbol}: {e}")
    
    def stop_all_streams(self):
        """Stop all active streams"""
        for stream_key in self.active_streams.copy():
            try:
                self.twm.stop_socket(stream_key)
            except:
                pass
        self.active_streams.clear()
    
    def handle_ticker_update(self, msg):
        """Handle ticker price updates"""
        try:
            data = {
                'symbol': msg['s'],
                'price': msg['c'],
                'priceChangePercent': msg['P'],
                'high24h': msg['h'],
                'low24h': msg['l'],
                'volume24h': msg['v']
            }
            socketio.emit('price_update', data)
        except Exception as e:
            logger.error(f"Error handling ticker update: {e}")
    
    def handle_depth_update(self, msg):
        """Handle order book depth updates"""
        try:
            data = {
                'symbol': msg['s'],
                'bids': msg['b'][:10],  # Top 10 bids
                'asks': msg['a'][:10]   # Top 10 asks
            }
            socketio.emit('orderbook_update', data)
        except Exception as e:
            logger.error(f"Error handling depth update: {e}")
    
    def handle_trade_update(self, msg):
        """Handle recent trades updates"""
        try:
            # Get recent trades from API (WebSocket trade events are individual)
            recent_trades = self.client.futures_recent_trades(symbol=self.current_symbol, limit=20)
            socketio.emit('recent_trades', recent_trades)
        except Exception as e:
            logger.error(f"Error handling trade update: {e}")
    
    def get_account_info(self):
        """Get account balance and information"""
        try:
            account_info = self.client.futures_account()
            return {
                'success': True,
                'data': {
                    'totalWalletBalance': account_info['totalWalletBalance'],
                    'availableBalance': account_info['availableBalance'],
                    'totalUnrealizedPnL': account_info['totalUnrealizedPnL'],
                    'assets': account_info['assets']
                }
            }
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_open_orders(self, symbol=None):
        """Get open orders"""
        try:
            orders = self.client.futures_get_open_orders(symbol=symbol)
            return {'success': True, 'data': orders}
        except Exception as e:
            logger.error(f"Error getting open orders: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_order_history(self, symbol=None, limit=50):
        """Get order history"""
        try:
            orders = self.client.futures_get_all_orders(symbol=symbol, limit=limit)
            return {'success': True, 'data': orders}
        except Exception as e:
            logger.error(f"Error getting order history: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_klines(self, symbol, interval='1m', limit=100):
        """Get candlestick data"""
        try:
            klines = self.client.futures_klines(symbol=symbol, interval=interval, limit=limit)
            return {'success': True, 'data': klines}
        except Exception as e:
            logger.error(f"Error getting klines: {e}")
            return {'success': False, 'error': str(e)}
    
    def place_order(self, order_data):
        """Place a trading order"""
        try:
            symbol = order_data['symbol']
            side = order_data['side']
            order_type = order_data['type']
            quantity = order_data['quantity']
            
            # Format quantity according to symbol precision
            formatted_qty = self.format_quantity(symbol, quantity)
            
            params = {
                'symbol': symbol,
                'side': side,
                'type': order_type,
                'quantity': formatted_qty
            }
            
            # Add price for limit orders
            if order_type in ['LIMIT', 'STOP_LIMIT'] and order_data.get('price'):
                params['price'] = str(order_data['price'])
                params['timeInForce'] = TIME_IN_FORCE_GTC
            
            # Add stop price for stop orders
            if order_type == 'STOP_LIMIT' and order_data.get('stopPrice'):
                params['stopPrice'] = str(order_data['stopPrice'])
            
            # Handle TWAP orders (execute as multiple market orders)
            if order_type == 'TWAP':
                return self.execute_twap_order(order_data)
            
            logger.info(f"Placing order: {params}")
            result = self.client.futures_create_order(**params)
            
            logger.info(f"✅ Order placed successfully: {result['orderId']}")
            return {
                'success': True,
                'orderId': result['orderId'],
                'data': result
            }
            
        except BinanceAPIException as e:
            logger.error(f"Binance API error placing order: {e}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return {'success': False, 'error': str(e)}
    
    def execute_twap_order(self, order_data):
        """Execute TWAP order as multiple market orders"""
        try:
            total_quantity = order_data['quantity']
            duration_minutes = order_data.get('twapDuration', 10)
            intervals = 5  # Split into 5 orders
            
            chunk_size = total_quantity / intervals
            interval_seconds = (duration_minutes * 60) / intervals
            
            logger.info(f"🕐 Starting TWAP execution: {intervals} orders over {duration_minutes} minutes")
            
            # Execute first order immediately
            first_order = self.place_market_order(order_data['symbol'], order_data['side'], chunk_size)
            
            if not first_order['success']:
                return first_order
            
            # Schedule remaining orders (simplified - in production use Celery or similar)
            threading.Timer(
                interval_seconds,
                self.execute_remaining_twap_orders,
                args=[order_data, chunk_size, interval_seconds, intervals - 1]
            ).start()
            
            return {
                'success': True,
                'orderId': first_order['orderId'],
                'message': f'TWAP execution started - {intervals} orders over {duration_minutes} minutes'
            }
            
        except Exception as e:
            logger.error(f"Error executing TWAP order: {e}")
            return {'success': False, 'error': str(e)}
    
    def execute_remaining_twap_orders(self, order_data, chunk_size, interval_seconds, remaining):
        """Execute remaining TWAP orders"""
        if remaining <= 0:
            logger.info("✅ TWAP execution completed")
            return
        
        try:
            # Place market order for this chunk
            result = self.place_market_order(order_data['symbol'], order_data['side'], chunk_size)
            
            if result['success']:
                logger.info(f"📊 TWAP Progress: {5 - remaining + 1}/5 completed")
            
            # Schedule next order if more remaining
            if remaining > 1:
                threading.Timer(
                    interval_seconds,
                    self.execute_remaining_twap_orders,
                    args=[order_data, chunk_size, interval_seconds, remaining - 1]
                ).start()
            else:
                logger.info("✅ TWAP execution completed")
                
        except Exception as e:
            logger.error(f"Error in TWAP execution: {e}")
    
    def place_market_order(self, symbol, side, quantity):
        """Place a market order"""
        try:
            formatted_qty = self.format_quantity(symbol, quantity)
            
            params = {
                'symbol': symbol,
                'side': side,
                'type': ORDER_TYPE_MARKET,
                'quantity': formatted_qty
            }
            
            result = self.client.futures_create_order(**params)
            
            return {
                'success': True,
                'orderId': result['orderId'],
                'data': result
            }
            
        except Exception as e:
            logger.error(f"Error placing market order: {e}")
            return {'success': False, 'error': str(e)}
    
    def cancel_order(self, symbol, order_id):
        """Cancel an order"""
        try:
            result = self.client.futures_cancel_order(symbol=symbol, orderId=order_id)
            logger.info(f"✅ Order cancelled: {order_id}")
            return {'success': True, 'data': result}
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return {'success': False, 'error': str(e)}
    
    def format_quantity(self, symbol, quantity):
        """Format quantity according to symbol precision"""
        try:
            info = self.client.futures_exchange_info()
            symbol_info = next((s for s in info['symbols'] if s['symbol'] == symbol), None)
            
            if symbol_info:
                # Find LOT_SIZE filter
                lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
                if lot_size_filter:
                    step_size = float(lot_size_filter['stepSize'])
                    precision = len(str(step_size).split('.')[-1].rstrip('0'))
                    return f"{quantity:.{precision}f}"
            
            return f"{quantity:.6f}"
            
        except Exception as e:
            logger.error(f"Error formatting quantity: {e}")
            return f"{quantity:.6f}"
    
    def cleanup(self):
        """Cleanup resources"""
        try:
            if self.twm:
                self.stop_all_streams()
                self.twm.stop()
                logger.info("✅ WebSocket manager stopped")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

# Initialize trading backend
trading_backend = TradingDashboardBackend()

# Flask Routes
@app.route('/')
def index():
    """Serve the main dashboard"""
    return render_template('index.html')

@app.route('/api/account/balance')
def get_account_balance():
    """Get account balance"""
    return jsonify(trading_backend.get_account_info())

@app.route('/api/orders/open')
def get_open_orders():
    """Get open orders"""
    symbol = request.args.get('symbol')
    return jsonify(trading_backend.get_open_orders(symbol))

@app.route('/api/orders/history')
def get_order_history():
    """Get order history"""
    symbol = request.args.get('symbol')
    limit = int(request.args.get('limit', 50))
    return jsonify(trading_backend.get_order_history(symbol, limit))

@app.route('/api/klines/<symbol>')
def get_klines(symbol):
    """Get candlestick data"""
    interval = request.args.get('interval', '1m')
    limit = int(request.args.get('limit', 100))
    return jsonify(trading_backend.get_klines(symbol, interval, limit))

@app.route('/api/orders/place', methods=['POST'])
def place_order():
    """Place a trading order"""
    try:
        order_data = request.get_json()
        
        # Validate required fields
        required_fields = ['symbol', 'side', 'type', 'quantity']
        for field in required_fields:
            if field not in order_data:
                return jsonify({'success': False, 'error': f'Missing field: {field}'})
        
        result = trading_backend.place_order(order_data)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in place_order route: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/orders/cancel', methods=['POST'])
def cancel_order():
    """Cancel an order"""
    try:
        data = request.get_json()
        symbol = data.get('symbol')
        order_id = data.get('orderId')
        
        if not symbol or not order_id:
            return jsonify({'success': False, 'error': 'Missing symbol or orderId'})
        
        result = trading_backend.cancel_order(symbol, order_id)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in cancel_order route: {e}")
        return jsonify({'success': False, 'error': str(e)})

# WebSocket Events
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info("Client connected")
    emit('connection_status', {'status': 'connected'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info("Client disconnected")

@socketio.on('subscribe_symbol')
def handle_subscribe_symbol(symbol):
    """Handle symbol subscription"""
    logger.info(f"Client subscribed to {symbol}")
    trading_backend.subscribe_to_symbol(symbol)

@socketio.on('request_account_update')
def handle_account_update():
    """Handle account update request"""
    account_info = trading_backend.get_account_info()
    if account_info['success']:
        emit('account_update', account_info['data'])

@socketio.on('request_orders_update')
def handle_orders_update():
    """Handle orders update request"""
    orders = trading_backend.get_open_orders()
    if orders['success']:
        emit('orders_update', orders['data'])

# Error Handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

# Startup and cleanup
def startup():
    """Application startup"""
    logger.info("🚀 Starting Professional Trading Dashboard")
    
    # Check environment variables
    required_env_vars = ['BINANCE_API_KEY', 'BINANCE_API_SECRET']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing environment variables: {missing_vars}")
        logger.error("Please create a .env file with your Binance API credentials")
        logger.error("Example .env file:")
        logger.error("BINANCE_API_KEY=your_api_key_here")
        logger.error("BINANCE_API_SECRET=your_api_secret_here")
        logger.error("BINANCE_TESTNET=true")
        exit(1)
    
    # Start WebSocket manager
    trading_backend.start_websocket_manager()
    
    logger.info("✅ Trading Dashboard Backend Ready")

def cleanup():
    """Application cleanup"""
    logger.info("🛑 Shutting down Trading Dashboard")
    trading_backend.cleanup()

if __name__ == '__main__':
    try:
        startup()
        
        # Run the Flask-SocketIO app
        socketio.run(
            app,
            host='0.0.0.0',
            port=5000,
            debug=False,  # Set to False for production
            allow_unsafe_werkzeug=True
        )
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Application error: {e}")
    finally:
        cleanup()