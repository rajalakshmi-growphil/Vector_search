const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

function run(command, cwd = '.') {
    console.log(`\nRunning: ${command} in ${cwd}`);
    execSync(command, { stdio: 'inherit', cwd: path.join(__dirname, '..', cwd) });
}

try {
    // 1. Infrastructure (Initial)
    console.log('🏗 Step 1: Deploying Infrastructure (Initial)...');
    run('terraform init', 'terraform');
    run('terraform apply -auto-approve', 'terraform');

    const adminBucket = execSync('terraform output -raw s3_admin_bucket', { cwd: path.join(__dirname, '../terraform') }).toString().trim();
    const customerBucket = execSync('terraform output -raw s3_customer_bucket', { cwd: path.join(__dirname, '../terraform') }).toString().trim();

    // 2. Backend
    console.log('\n⚡ Step 2: Deploying Serverless Backend...');
    run('npm install', 'backend');
    run('npx serverless deploy', 'backend');

    // Get API Endpoint from Serverless
    console.log('   Retrieving API Endpoint...');
    const slsInfo = execSync('npx serverless info --verbose', { cwd: path.join(__dirname, '../backend') }).toString();
    const apiEndpointMatch = slsInfo.match(/HttpApi: (https:\/\/[a-z0-9]+\.execute-api\.[a-z0-9-]+\.amazonaws\.com)/);

    if (!apiEndpointMatch) {
        throw new Error("Could not retrieve API Endpoint from Serverless info");
    }
    const apiEndpoint = 'https://api.lakshmi-dev.site';
    console.log(`\nAPI Endpoint (Custom): ${apiEndpoint}`);

    // Still extract for CloudFront origin update if needed
    const apiDomainGenerated = apiEndpointMatch[1].replace('https://', '');

    // 3. Infrastructure (Update CloudFront)
    console.log('\n🔄 Step 3: Updating CloudFront Origin...');
    // We update terraform with the generated domain for the origin, 
    // but the frontend will use the custom domain for calls.
    run(`terraform apply -auto-approve -var="api_gateway_domain=${apiDomainGenerated}"`, 'terraform');

    // 4. Update Frontend
    console.log('\n📝 Step 4: Updating Frontend Configurations...');
    const adminPath = path.join(__dirname, '../admin/index.html');
    const customerPath = path.join(__dirname, '../customer/index.html');

    let adminContent = fs.readFileSync(adminPath, 'utf8');
    adminContent = adminContent.replace(/const API_BASE_URL = '.*'/, `const API_BASE_URL = '${apiEndpoint}'`);
    fs.writeFileSync(adminPath, adminContent);

    let customerContent = fs.readFileSync(customerPath, 'utf8');
    customerContent = customerContent.replace(/const API_URL = '.*'/, `const API_URL = '${apiEndpoint}'`);
    fs.writeFileSync(customerPath, customerContent);

    // 5. Frontend Sync
    console.log('\n🌐 Step 5: Syncing Frontend to S3...');
    run(`aws s3 sync admin/ s3://${adminBucket} --delete`);
    run(`aws s3 sync customer/ s3://${customerBucket} --delete`);

    console.log('\n🎉 Unified Deployment Successful!');
} catch (error) {
    console.error('\n❌ Deployment Failed:', error.message);
    process.exit(1);
}
