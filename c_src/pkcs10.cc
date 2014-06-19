#include <botan/init.h>
#include <botan/auto_rng.h>
#include <botan/x509self.h>
#include <botan/rsa.h>
#include <botan/dsa.h>
using namespace Botan;

#include <iostream>
#include <fstream>
#include <memory>

#define KEY_SIZE 4096

int create_csr(char* password, char* key_path, char* csr_path)
{
    Botan::LibraryInitializer init;
    try
    {
        AutoSeeded_RNG rng;
        RSA_PrivateKey priv_key(rng, KEY_SIZE);
        std::ofstream key_file(key_path);
        key_file << PKCS8::PEM_encode(priv_key, rng, std::string(password));

        X509_Cert_Options opts;

        opts.common_name = "CN";
        opts.country = "PL";
        opts.organization = "";
        opts.email = "";

        PKCS10_Request req = X509::create_cert_req(opts, priv_key, "SHA-256", rng);

        std::ofstream req_file(csr_path);
        req_file << req.PEM_encode();
    }
    catch(std::exception& e)
    {
        std::cout << e.what() << std::endl;
        return 1;
    }
    return 0;
}
