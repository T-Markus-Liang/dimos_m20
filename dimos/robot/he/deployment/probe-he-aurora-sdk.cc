#include <cctype>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include "deptrum/aurora900_series.h"
#include "deptrum/device.h"

namespace {

std::string JsonEscape(const std::string& value) {
  std::ostringstream output;
  for (const unsigned char character : value) {
    switch (character) {
      case '\\': output << "\\\\"; break;
      case '"': output << "\\\""; break;
      case '\n': output << "\\n"; break;
      case '\r': output << "\\r"; break;
      case '\t': output << "\\t"; break;
      default:
        if (character < 0x20) {
          output << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                 << static_cast<int>(character) << std::dec;
        } else {
          output << character;
        }
    }
  }
  return output.str();
}

std::string DataHex(const deptrum::stream::Data& data) {
  if (data.data_len <= 0 || data.data == nullptr || data.data_len > 1024) return "";
  std::ostringstream output;
  for (int index = 0; index < data.data_len; ++index) {
    if (index) output << ' ';
    output << std::hex << std::setw(2) << std::setfill('0')
           << static_cast<int>(static_cast<unsigned char>(data.data[index]));
  }
  return output.str();
}

std::string DataAscii(const deptrum::stream::Data& data) {
  if (data.data_len <= 0 || data.data == nullptr || data.data_len > 1024) return "";
  std::string output;
  output.reserve(data.data_len);
  for (int index = 0; index < data.data_len; ++index) {
    const unsigned char value = data.data[index];
    output.push_back(std::isprint(value) ? static_cast<char>(value) : '.');
  }
  return output;
}

template <typename T, std::size_t Size>
void PrintArray(std::ostream& output, const T (&values)[Size]) {
  output << '[';
  for (std::size_t index = 0; index < Size; ++index) {
    if (index) output << ',';
    output << values[index];
  }
  output << ']';
}

template <typename T>
void PrintNullable(std::ostream& output, int status, const T& value) {
  if (status == 0) {
    output << value;
  } else {
    output << "null";
  }
}

void PrintNullableString(std::ostream& output, int status, const std::string& value) {
  if (status == 0) {
    output << '"' << JsonEscape(value) << '"';
  } else {
    output << "null";
  }
}

}  // namespace

int main(int argc, char** argv) {
  using deptrum::Extrinsic;
  using deptrum::Intrinsic;
  using deptrum::stream::Aurora900;
  using deptrum::stream::Device;
  using deptrum::stream::DeviceDescription;
  using deptrum::stream::DeviceManager;
  using deptrum::stream::SupportedInfo;

  if (argc != 2) {
    std::cerr << "Usage: he-aurora-sdk-probe OUTPUT.json\n";
    return 1;
  }

  DeviceManager::GetInstance()->RegisterDeviceConnectedCallback(nullptr, false);
  std::vector<deptrum::DeviceInformation> devices;
  const int list_status = DeviceManager::GetInstance()->GetDeviceList(devices);
  if (list_status != 0 || devices.size() != 1) {
    std::cerr << "Expected exactly one Aurora device; status=" << list_status
              << " count=" << devices.size() << '\n';
    return 2;
  }

  std::shared_ptr<Device> device = DeviceManager::GetInstance()->CreateDevice(devices.front());
  if (!device) {
    std::cerr << "CreateDevice returned null\n";
    return 3;
  }
  const int open_status = device->Open();
  if (open_status != 0) {
    std::cerr << "Open failed: " << open_status << '\n';
    return 4;
  }

  const auto aurora = std::dynamic_pointer_cast<Aurora900>(device);
  if (!aurora) {
    device->Close();
    std::cerr << "Connected device is not an Aurora900-series device\n";
    return 5;
  }

  const std::string sdk_version = device->GetSdkVersion();

  DeviceDescription description{};
  SupportedInfo support{};
  Intrinsic ir_intrinsic{};
  Intrinsic rgb_intrinsic{};
  Extrinsic rgb_to_ir{};
  int16_t camera_temperature = 0;
  int16_t vcsel_temperature = 0;
  int16_t cpu_temperature = 0;
  int laser_current_ma = 0;

  const int device_info_status = aurora->GetDeviceInfo(description);
  const int support_status = aurora->GetSupportInfo(support);
  const int parameters_status =
      device->GetCameraParameters(ir_intrinsic, rgb_intrinsic, rgb_to_ir);
  const int camera_temperature_status = aurora->GetCameraTemperature(
      deptrum::stream::kTemperatureCamera, &camera_temperature);
  const int vcsel_temperature_status = aurora->GetCameraTemperature(
      deptrum::stream::kTemperatureVcsel, &vcsel_temperature);
  const int cpu_temperature_status = aurora->GetCameraTemperature(
      deptrum::stream::kTemperatureCpu, &cpu_temperature);
  const int laser_current_status = aurora->GetLaserCurrent(laser_current_ma);
  const int close_status = device->Close();

  std::ofstream report(argv[1]);
  if (!report) {
    std::cerr << "Cannot open output file: " << argv[1] << '\n';
    return 7;
  }
  report << std::setprecision(9);
  report << "{\n  \"device_count\": 1,\n  \"sdk_version\": \""
         << JsonEscape(sdk_version) << "\",\n  \"device_name\": ";
  PrintNullableString(report, device_info_status, description.device_name);
  report << ",\n  \"stream_sdk_version\": ";
  PrintNullableString(report, device_info_status, description.stream_sdk_version);
  report << ",\n  \"rgb_firmware_version\": ";
  PrintNullableString(report, device_info_status, description.rgb_firmware_version);
  report << ",\n  \"ir_firmware_version\": ";
  PrintNullableString(report, device_info_status, description.ir_firmware_version);
  report << ",\n  \"vid\": ";
  PrintNullable(report, device_info_status, description.vid);
  report << ",\n  \"pid\": ";
  PrintNullable(report, device_info_status, description.pid);
  report << ",\n  \"return_codes\": {\n"
         << "    \"device_info\": " << device_info_status << ",\n"
         << "    \"support_info\": " << support_status << ",\n"
         << "    \"camera_parameters\": " << parameters_status << ",\n"
         << "    \"camera_temperature\": " << camera_temperature_status << ",\n"
         << "    \"vcsel_temperature\": " << vcsel_temperature_status << ",\n"
         << "    \"cpu_temperature\": " << cpu_temperature_status << ",\n"
         << "    \"laser_current\": " << laser_current_status << ",\n"
         << "    \"close\": " << close_status << "\n  },\n  \"support\": ";
  if (support_status == 0) {
    report << "{\n    \"scan_face_mode\": " << static_cast<int>(support.scan_face_mode)
           << ",\n    \"scan_code_mode\": " << static_cast<int>(support.scan_code_mode)
           << ",\n    \"running_7x24_hours\": "
           << static_cast<int>(support.running_7x24_hours)
           << ",\n    \"secure_encryption\": " << static_cast<int>(support.is_support_se)
           << ",\n    \"synced_two_images\": "
           << static_cast<int>(support.is_support_synced_2_img)
           << ",\n    \"depth_range_length\": " << support.depth_range.data_len
           << ",\n    \"depth_range_hex\": \"" << DataHex(support.depth_range)
           << "\",\n    \"depth_range_ascii\": \""
           << JsonEscape(DataAscii(support.depth_range)) << "\"\n  }";
  } else {
    report << "null";
  }
  report << ",\n  \"temperature_raw\": {\"camera\": ";
  PrintNullable(report, camera_temperature_status, camera_temperature);
  report << ", \"vcsel\": ";
  PrintNullable(report, vcsel_temperature_status, vcsel_temperature);
  report << ", \"cpu\": ";
  PrintNullable(report, cpu_temperature_status, cpu_temperature);
  report << "},\n  \"laser_current_ma\": ";
  PrintNullable(report, laser_current_status, laser_current_ma);
  report << ",\n  \"ir_intrinsic\": ";
  if (parameters_status == 0) {
    report << "{\"rows\": " << ir_intrinsic.rows << ", \"cols\": " << ir_intrinsic.cols
           << ", \"focal_length\": ";
    PrintArray(report, ir_intrinsic.focal_length);
    report << ", \"principal_point\": ";
    PrintArray(report, ir_intrinsic.principal_point);
    report << '}';
  } else {
    report << "null";
  }
  report << ",\n  \"rgb_intrinsic\": ";
  if (parameters_status == 0) {
    report << "{\"rows\": " << rgb_intrinsic.rows << ", \"cols\": "
           << rgb_intrinsic.cols << ", \"focal_length\": ";
    PrintArray(report, rgb_intrinsic.focal_length);
    report << ", \"principal_point\": ";
    PrintArray(report, rgb_intrinsic.principal_point);
    report << '}';
  } else {
    report << "null";
  }
  report << ",\n  \"rgb_to_ir_extrinsic\": ";
  if (parameters_status == 0) {
    report << "{\"rotation_row_major\": ";
    PrintArray(report, rgb_to_ir.rotation_matrix);
    report << ", \"translation_mm\": ";
    PrintArray(report, rgb_to_ir.translation_vector);
    report << '}';
  } else {
    report << "null";
  }
  report << "\n}\n";

  return close_status == 0 ? 0 : 6;
}
