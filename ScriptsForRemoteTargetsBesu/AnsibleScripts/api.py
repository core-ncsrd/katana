from flask import Flask, request, jsonify
import ansible_runner

app = Flask(__name__)

@app.route('/run_playbook', methods=['POST'])
def run_playbook():
    # Parse JSON input
    data = request.get_json()
    playbook = data.get('playbook', 'start_nodes.yml')
    private_data_dir = data.get('private_data_dir', '~/besu-ansible')
    extra_vars = data.get('extra_vars', {})

    # Run the playbook using ansible-runner
    result = ansible_runner.run(
        private_data_dir=private_data_dir,
        playbook=playbook,
        extravars=extra_vars
    )

    # Prepare the response with basic details
    response = {
        'status': result.status,
        'rc': result.rc,
        'stdout': result.stdout.read() if result.stdout else ''
    }
    return jsonify(response)

if __name__ == '__main__':
    # Run the Flask app on all interfaces at port 5000
    app.run(host='0.0.0.0', port=5000)