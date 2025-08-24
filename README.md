# Luna Agent

> DO NOT commit to the main branch, commit to a new branch make PR for merging

> DO NOT operate under /root/vv/LunaAgent, ANY changes in this directory will be reset by `git reset --hard`

> 不要向 main 分支 commit, commit 到新分支并提PR.

> 不要进入 /root/vv/LunaAgent 进行**任何**操作，所有改动将被 `git reset --hard`


## How to start a local service for development

### Clone this repo

```bash
git clone git@ysgit.lunalabs.cn:lunalabs/luna-models/LunaAgent.git && cd LunaAgent
```

### Setup conda env

#### Option 1: use existing env on 4090-1


```bash
# although it is recoverable, try not to mess up this env
# if you need to pip / conda install new packages, go to option 2
conda activate luna-agent
```


#### Option 2: create a new env

```bash
conda create -n luna-agent-dev-<your_alias> python=3.10
conda activate luna-agent-dev-<your_alias>
pip install -e ./
```

### Start services

Start 3 tmux panels and run these command to start chat agent, websocket middleware and webui frontend:

1. Agent:
    ```bash
    source env.sh
    PYTHONPATH=./luna_agent python luna_agent/chat.py
    ```
2. Websocket:
    ```bash
    source env.sh
    cd debug && python middleware.py
    ```

3. WebUI:
    ```bash
    source env.sh
    cd debug && python app.py
    ```

### SSL port forward

On your local machine, run the following command with ports set in env.sh:
```bash
ssh -N -L 28001:localhost:28001 -L 28002:localhost:28002 -L 28003:localhost:28003 4090-1
```

Open http://localhost:28003 and start session. Note that the frontend is simplified for development with chat functions only. Contact 蒋鹏 for deployment.


## How to commit (TBD)

You should create pull requests (PR) to merge changes to the main branch. But deleting a repo seems not possible by now...

### Temperary solution:

Commit and push to a new branch, contact 王巍 to merge into the main branch (code review required).

NEVER commit to the main branch.


# Luna Models

Under Construction