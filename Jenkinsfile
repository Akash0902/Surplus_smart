pipeline {
    agent any

    stages {
        stage('Build') {
            steps {
                echo 'Building application'
            }
        }
    }

    post {
        always {
            emailext(
                to: 'akash@example.com',
                subject: "Build Status: ${currentBuild.currentResult}",
                body: """
                Job: ${env.JOB_NAME}
                Build Number: ${env.BUILD_NUMBER}
                Status: ${currentBuild.currentResult}
                URL: ${env.BUILD_URL}
                """
            )
        }
    }
}
``
