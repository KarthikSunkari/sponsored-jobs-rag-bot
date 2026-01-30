"""
Simple Flask API for embedding generation (called by n8n).
"""
from flask import Flask, request, jsonify
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from rag.embedding_service import get_embedding_service
from utils.supabase_client import get_supabase_client

app = Flask(__name__)


@app.route('/generate-embedding', methods=['POST'])
def generate_embedding():
    """Generate and store embedding for a job description."""
    data = request.json
    job_id = data.get('job_id')
    description = data.get('description', '')
    
    if not job_id or not description:
        return jsonify({'error': 'job_id and description required'}), 400
    
    try:
        # Generate embedding
        embedding_service = get_embedding_service()
        embedding = embedding_service.encode(description)
        
        # Store in database
        client = get_supabase_client()
        result = client.insert_job_embedding(job_id, embedding)
        
        if result:
            return jsonify({'success': True, 'job_id': job_id})
        else:
            return jsonify({'error': 'Failed to store embedding'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'healthy'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
