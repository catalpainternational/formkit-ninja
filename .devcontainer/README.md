# Building Production Ready Images


docker build --target final_prod -f Dockerfile ..


# Building Dev Images

The 'dev' image is created using build args and a target, see the `docker.compose` file