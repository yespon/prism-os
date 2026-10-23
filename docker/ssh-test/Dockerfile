ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}
RUN apt-get update && apt-get install -y --no-install-recommends openssh-server bash coreutils \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/ssh/ssh_host_*_key /etc/ssh/ssh_host_*_key.pub \
    && useradd --create-home --shell /bin/bash target \
    && usermod --password x target
COPY sshd_config /etc/ssh/prismos-test.conf
COPY entry.sh /usr/local/bin/prismos-ssh-test
RUN chmod 755 /usr/local/bin/prismos-ssh-test \
    && printf 'unset HISTFILE\n' > /home/target/.bashrc
ARG TEST_MARKER=PRISMOS_SSH_TEST
RUN printf '%s\n' "${TEST_MARKER}" > /home/target/fixture.txt \
    && chmod 444 /home/target/fixture.txt
LABEL prismos.test.kind="ssh-target"
WORKDIR /home/target
EXPOSE 2222
ENTRYPOINT ["/usr/local/bin/prismos-ssh-test"]
