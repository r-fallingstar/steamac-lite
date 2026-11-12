// SPDX-License-Identifier: Apache-2.0
// Explicit controller-local calibration; no guessed profile defaults.
#pragma once
#include <cerrno>
#include <cctype>
#include <cstdlib>
#include "vrmath.h"

namespace svr {
struct ControllerOffset {
  float translation[3] = {};
  Quat rotation{};
  bool enabled = false;
};

// Values describe the right hand: metres, then optional local XYZ Euler degrees.
// Reflection in the YZ plane negates translation X and rotation Y/Z for the left.
inline bool parse_controller_offset(const char *text, bool left, ControllerOffset &out) {
  out = {};
  if (!text || !*text) return true;
  float v[6] = {};
  unsigned count = 0;
  const char *cursor = text;
  while (true) {
    if (count == 6) return false;
    char *end;
    errno = 0;
    v[count] = std::strtof(cursor, &end);
    if (end == cursor || errno == ERANGE || !std::isfinite(v[count])) return false;
    if (std::fabs(v[count]) > (count < 3 ? 10.0f : 360.0f)) return false;
    ++count;
    while (std::isspace(static_cast<unsigned char>(*end))) ++end;
    if (!*end) break;
    if (*end != ',') return false;
    cursor = end + 1;
  }
  if (count != 3 && count != 6) return false;
  if (left) v[0] = -v[0], v[4] = -v[4], v[5] = -v[5];
  constexpr float half_rad = 3.14159265358979323846f / 360.0f;
  Quat x{std::sin(v[3] * half_rad), 0, 0, std::cos(v[3] * half_rad)};
  Quat y{0, std::sin(v[4] * half_rad), 0, std::cos(v[4] * half_rad)};
  Quat z{0, 0, std::sin(v[5] * half_rad), std::cos(v[5] * half_rad)};
  for (int i = 0; i < 3; ++i) out.translation[i] = v[i];
  out.rotation = qnorm(qmul(qmul(x, y), z));
  out.enabled = true;
  return true;
}

inline svr_pose offset_controller_pose(const svr_pose &p, const ControllerOffset &offset) {
  if (!offset.enabled) return p;
  svr_pose result = p;
  Quat orientation{p.orientation[0], p.orientation[1], p.orientation[2], p.orientation[3]};
  float t[3];
  qrot(orientation, offset.translation, t);
  for (int i = 0; i < 3; ++i) result.position[i] += t[i];
  Quat q = qnorm(qmul(orientation, offset.rotation));
  result.orientation[0] = q.x; result.orientation[1] = q.y;
  result.orientation[2] = q.z; result.orientation[3] = q.w;
  if (p.flags & SVR_POSE_VEL) {
    // Velocity belongs to the new reference point: v' = v + omega x (R*t).
    result.lin_vel[0] += p.ang_vel[1] * t[2] - p.ang_vel[2] * t[1];
    result.lin_vel[1] += p.ang_vel[2] * t[0] - p.ang_vel[0] * t[2];
    result.lin_vel[2] += p.ang_vel[0] * t[1] - p.ang_vel[1] * t[0];
  }
  return result;
}

struct ControllerOffsets {
  ControllerOffset grip[2], aim[2];
  bool load(const char *grip_text, const char *aim_text) {
    ControllerOffsets parsed;
    for (int hand = 0; hand < 2; ++hand) {
      if (!parse_controller_offset(grip_text, hand == 0, parsed.grip[hand]) ||
          !parse_controller_offset(aim_text, hand == 0, parsed.aim[hand])) {
        *this = {};
        return false;
      }
    }
    *this = parsed;
    return true;
  }
  svr_pose apply(int dev, const svr_pose &p) const {
    switch (dev) {
      case SVR_DEV_LEFT_GRIP: return offset_controller_pose(p, grip[0]);
      case SVR_DEV_RIGHT_GRIP: return offset_controller_pose(p, grip[1]);
      case SVR_DEV_LEFT_AIM: return offset_controller_pose(p, aim[0]);
      case SVR_DEV_RIGHT_AIM: return offset_controller_pose(p, aim[1]);
      default: return p;
    }
  }
};
} // namespace svr
